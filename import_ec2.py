from utils.utilities import Utilities, SkipTag
from jinja2 import Environment, FileSystemLoader
from loguru import logger
import os
from botocore.exceptions import ClientError
from utils.cleanup import cleanup_tf_plan_file
import sys
import re


class EC2ImportSetUp:
    """
    Import Block for EC2 Import.
    Supoprted resources: EC2, EBS, Route53
    Note: Target Group Attachement resource import is not supported by Provider
    """

    def __init__(self, region, resource, local_repo_path, hosted_zone_name, filters):
        self.client = Utilities.create_session(region=region, resource=resource)
        self.tmpl = Environment(loader=FileSystemLoader("templates"))
        self.region = region
        self.local_repo_path = local_repo_path
        self.hosted_zone_name = hosted_zone_name
        self.tag_filters = {key: value for key, value in filters} if filters else {}

    def get_hosted_zone_id(self, vpc_id):
        """
        Get Hosted Zone ID from Zone Name.
        """
        client = Utilities.create_client(region=self.region, resource="route53")
        # List hosted zones associated with the given VPC
        response = client.list_hosted_zones_by_vpc(VPCId=vpc_id, VPCRegion=self.region)

        hosted_zones = response.get("HostedZoneSummaries", [])
        for zone in hosted_zones:
            if zone["Name"] == f"{self.hosted_zone_name}.":
                return zone["HostedZoneId"]
        return None
    
    def sanitize_name(self, filename):
        # Replace invalid characters with an underscore
        return re.sub(r'[<>:"/\\|?*]', "_", filename)

    def describe_instance(self):
        """
        Get Instance details
        """
        # Filter instances based on tags
        filters = [{"Name": f"tag:{key}", "Values": [value]} for key, value in self.tag_filters.items()]
        # Add a filter to exclude terminated instances
        filters.append({"Name": "instance-state-name", "Values": ["pending", "running", "shutting-down", "stopping", "stopped"]})

        instances = self.client.instances.filter(Filters=filters)
        instance_details = []

        for instance in instances:
            instance_tags = {tag['Key']: tag['Value'] for tag in instance.tags}
            #Skip instances with the TF_IMPORTED tag set to true
            if instance_tags.get('TF_IMPORTED') == SkipTag.TF_IMPORTED.value :
               logger.info(f"Skipping Instance {instance.id} where TF_IMPORTED tag is set")
               continue
            
            instance_info = {"instance_id": instance.id, "private_ip": instance.private_ip_address, "vpc_id": instance.vpc_id, "instance_name": None, "Volumes": []}

            for tag in instance.tags:
                if tag["Key"] == "Name":
                    instance_info["instance_name"] = self.sanitize_name(tag["Value"])
                    break

            for volume in instance.volumes.all():
                volume_type = volume.volume_type
                root_device_name = instance.root_device_name
                attachment = volume.attachments[0]

                attachment_info = {"VolumeId": volume.id, "VolumeType": volume_type, "Device": attachment["Device"], "AttachmentType": "root" if attachment["Device"] == root_device_name else "data"}
                instance_info["Volumes"].append(attachment_info)

            instance_details.append(instance_info)
        logger.info(f"Total EC2 Instances Found: { len(instance_details) }")
        return instance_details

    def check_dns_record(self, ip, hosted_zone_id):
        """
        Get Instance DNS Record
        """
        client = Utilities.create_client(region=self.region, resource="route53")
        # Retrieve the list of record sets for the specified hosted zone
        paginator = client.get_paginator("list_resource_record_sets")
        record_sets = paginator.paginate(HostedZoneId=hosted_zone_id)

        record_found = False
        record_name = None
        try:
            for page in record_sets:
                for record_set in page["ResourceRecordSets"]:
                    for record in record_set.get("ResourceRecords", []):
                        if record["Value"] == ip:
                            record_name = record_set["Name"]
                            record_found = True
                            break
                if record_found:
                    break
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchHostedZone":
                logger.error(f"No hosted zone found with ID: {hosted_zone_id}")
            return False, None

        return record_found, record_name

    def generate_import_blocks(self, instance_details):
        """
        Generate Import Blocks, Generate Terraform code, Cleanup Terraform code
        """
        if not instance_details:
            logger.info("No instance found: Nothing to do. Exitting")
            sys.exit(1)
        template = self.tmpl.get_template("ec2_import.tf.j2")

        hosted_zone_id = self.get_hosted_zone_id(instance_details[0]["vpc_id"])
        if hosted_zone_id is None:
            logger.error(f"Hosted Route53 Zone doesn't Exist , Please Verify: {self.hosted_zone_name}")
            sys.exit(1)
        
        for instance in instance_details:
            logger.info(f"Importing : {instance}")

            is_dns_exist, record_name = self.check_dns_record(ip=instance["private_ip"], hosted_zone_id=hosted_zone_id)

            context = {"instance_details": instance, "zone_id": hosted_zone_id, "zone_name": self.hosted_zone_name, "dns_record_name": record_name if is_dns_exist else ""}

            rendered_template = template.render(context)

            output_file_path = f"{self.local_repo_path}/import-{instance['instance_name']}.tf"
            with open(output_file_path, "w") as f:
                f.write(rendered_template)

            Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan", f"-generate-config-out=generated-plan-import-{instance['instance_name']}.tf"])
            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(input_tf_file=f"{self.local_repo_path}/generated-plan-import-{instance['instance_name']}.tf")

        for filename in os.listdir(self.local_repo_path):
            if filename.endswith(".imported"):
                new_filename = filename.replace(".imported", "")
                old_file = os.path.join(self.local_repo_path, filename)
                new_file = os.path.join(self.local_repo_path, new_filename)
                os.rename(old_file, new_file)

    def set_everything(self):
        """
        Setup the WorkFlow Steps.
        """
        Utilities.generate_tf_provider(self.local_repo_path, region=self.region)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "init"])

        instances = self.describe_instance()
        self.generate_import_blocks(instances)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"])
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"])
