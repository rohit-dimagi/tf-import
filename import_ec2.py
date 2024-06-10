from utils.utilities import Utilities
from jinja2 import Environment, FileSystemLoader
from loguru import logger

class EC2ImportSetUp:
    """
    Cleanup Gold AMI and it"s snapshot which is no longer needed.
    """

    def __init__(self, environment, workspace, region, resource, local_repo_path, hosted_zone_name, filters):
        self.client = Utilities.create_session(region=region, resource=resource)
        self.tmpl = Environment(loader=FileSystemLoader('templates'))
        self.region = region
        self.local_repo_path = local_repo_path
        self.resource_name = f"{environment}_{region}_ec2_"
        self.workspace = workspace
        self.hosted_zone_name = hosted_zone_name
        self.tag_filters = {key: value for key, value in filters} if filters else {}

    def get_hosted_zone_id(self, vpc_id):
        client = Utilities.create_client(region=self.region, resource="route53")
        # List hosted zones associated with the given VPC
        response = client.list_hosted_zones_by_vpc(
            VPCId=vpc_id,
            VPCRegion=self.region 
        )
        
        hosted_zones = response.get('HostedZoneSummaries', [])
        for zone in hosted_zones:
            if zone['Name'] == f"{self.hosted_zone_name}.":
                return zone['HostedZoneId']
    
    
    def describe_instance(self):
        """
        Get Instance details
        """
        # Filter instances based on tags
        filters = [{'Name': f'tag:{key}', 'Values': [value]} for key, value in self.tag_filters.items()]
        
        instances = self.client.instances.filter(Filters=filters)        
        instance_details = []
    
        for instance in instances:
            instance_info = {
                "instance_id": instance.id,
                'private_ip': instance.private_ip_address,
                'vpc_id': instance.vpc_id,
                "instance_name": None,
                "Volumes": []
            }
            
            for tag in instance.tags:
                if tag['Key'] == 'Name':
                    instance_info["instance_name"] = tag['Value']
                    break
            
            for volume in instance.volumes.all():
                volume_type = volume.volume_type
                root_device_name = instance.root_device_name
                attachment = volume.attachments[0]

                attachment_info = {
                    'VolumeId': volume.id,
                    'VolumeType': volume_type,
                    'Device': attachment['Device'],
                    'AttachmentType': 'root' if attachment['Device'] == root_device_name else 'data'
                }
                instance_info['Volumes'].append(attachment_info)

            instance_details.append(instance_info)
        logger.info(instance_details)
        return instance_details
        
    def generate_import_blocks(self, instance_details):
        output_file_path = f"{self.local_repo_path}/imports.tf"
        template = self.tmpl.get_template('ec2_import.tf.j2')
        
        hosted_zone_id = self.get_hosted_zone_id(instance_details[0]["vpc_id"])
        context = {
            'instance_details': instance_details,
            'resource_type': "aws_instance",
            'zone_id': hosted_zone_id,
            'zone_name': self.hosted_zone_name
        }

        rendered_template = template.render(context)

        with open(output_file_path, 'w') as f:
            f.write(rendered_template)
    

    def set_everything(self):
        instances = self.describe_instance()
        self.generate_import_blocks(instances)
        #Utilities.generate_tf_backend(self.local_repo_path,tfe_hostname="app.terraform.io", tfe_workspace="store-api-iac", tfe_org="rohit-kumar-hcp")
        Utilities.generate_tf_provider(self.local_repo_path, region=self.region)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "init"])
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan", f"-generate-config-out={self.resource_name}.tf"])
        Utilities.clean_generated_tf_code(resource="ec2", tf_file=f"{self.local_repo_path}/{self.resource_name}.tf")
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"])
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"])
