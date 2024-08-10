from utils.utilities import Utilities, SkipTag
from jinja2 import Environment, FileSystemLoader
from loguru import logger
import os
from botocore.exceptions import ClientError
from utils.cleanup import cleanup_tf_plan_file
import sys


class S3ImportSetUp:
    """
    Import Block for S3 Import.
    Supoprted resources: S3 Bucket
    """

    def __init__(self, region, resource, local_repo_path, filters, profile):
        self.client = Utilities.create_client(region=region, resource=resource, profile=profile)
        self.tmpl = Environment(loader=FileSystemLoader("templates"))
        self.region = region
        self.aws_profile = profile
        self.local_repo_path = local_repo_path
        self.tag_filters = {key: value for key, value in filters} if filters else {}

    def describe_s3_buckets(self):
        """
        Get details for all S3 Buckets, filtered by tags
        """
        # Retrieve the list of load balancers
        s3_buckets = self.client.list_buckets()["Buckets"]

        s3_bucket_details = []
        tags = {}

        for bucket in s3_buckets:
            bucket_name = bucket["Name"]

            try:
                # Retrieve tags for the bucket
                response = self.client.get_bucket_tagging(Bucket=bucket_name)
                tag_set = response['TagSet']
                tags = {tag['Key']: tag['Value'] for tag in tag_set}
            except Exception as e:
                pass

            # Check region for the bucket
            response = self.client.get_bucket_location(Bucket=bucket_name)
            bucket_region = response['LocationConstraint']
            if bucket_region != self.region:
                continue

            # Skip buckets if TF_IMPORTED tag is set to true
            if tags.get('TF_IMPORTED', 'false').lower() == 'true':
                continue

            bucket_detail = {
                "bucket_name": bucket_name,
                "bucket_policy": False,
                "bucket_acl": False,
                "bucket_versioning": False,
                "bucket_lifecycle_rule": False,
                "bucket_intelligent_tiering": False,
                "bucket_cors_config": False,
                "bucket_replication_config": False,
                "bucket_server_side_encryption": False,
            }

            # Check if the bucket has a policy
            try:
                self.client.get_bucket_policy(Bucket=bucket_name)
                bucket_detail["bucket_policy"] = True
            except ClientError:
                pass  # Bucket has no policy

            # Check if the bucket has ACL
            try:
                acl = self.client.get_bucket_acl(Bucket=bucket_name)
                bucket_detail["bucket_acl"] = bool(acl)
            except ClientError:
                pass

            # Check if versioning is enabled for the bucket
            try:
                versioning = self.client.get_bucket_versioning(Bucket=bucket_name)
                if versioning.get("Status") == "Enabled":
                    bucket_detail["bucket_versioning"] = True
            except ClientError:
                pass

            # Check if the bucket has a lifecycle configuration
            try:
                lifecycle = self.client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
                bucket_detail["bucket_lifecycle_rule"] = bool(lifecycle["Rules"])
            except ClientError:
                pass

            # Check if the bucket has a Intelligent tiering configuration
            try:
                intelligent_tiering = self.client.list_bucket_intelligent_tiering_configurations(Bucket=bucket_name)
                bucket_detail["bucket_intelligent_tiering"] = bool(intelligent_tiering.get('IntelligentTieringConfigurationList'))
            except ClientError:
                pass

            # Check if the bucket has a cors configuration
            try:
                cors = self.client.get_bucket_cors(Bucket=bucket_name)
                bucket_detail["bucket_cors_config"] = bool(cors.get('CORSRules'))
            except ClientError:
                pass

            # Check if the bucket has replication configuration
            try:
                replication = self.client.get_bucket_replication(Bucket=bucket_name)
                bucket_detail["bucket_replication_config"] =  bool(replication.get('ReplicationConfiguration'))
            except ClientError:
                pass

            # Check if the bucket has server side encryption configuration
            try:
                encryption = self.client.get_bucket_encryption(Bucket=bucket_name)
                bucket_detail["bucket_server_side_encryption"] = bool(encryption.get('ServerSideEncryptionConfiguration'))
            except ClientError:
                pass

            # Check if the bucket matches the tag filters
            if all(tags.get(key) == value for key, value in self.tag_filters.items()):
                s3_bucket_details.append(bucket_detail)

        logger.info(f"Total S3 Buckets Found: {len(s3_bucket_details)}")

        return s3_bucket_details


    def generate_import_blocks(self, s3_bucket_details):
        """
        Generate Import Blocks, Generate Terraform code, Cleanup Terraform code
        """
        if not s3_bucket_details:
            logger.info("No S3 Bucket found: Nothing to do. Exitting")
            sys.exit(1)

        template = self.tmpl.get_template("s3_import.tf.j2")

        for bucket in s3_bucket_details:
            logger.info(f"Importing : {bucket}")

            context = {
                "bucket_name": bucket["bucket_name"],
                "bucket_policy": bucket["bucket_policy"],
                "bucket_acl": bucket["bucket_acl"],
                "bucket_versioning": bucket["bucket_versioning"],
                "bucket_lifecycle_rule": bucket["bucket_lifecycle_rule"],
                "bucket_intelligent_tiering": bucket["bucket_intelligent_tiering"],
                "bucket_cors_config": bucket["bucket_cors_config"],
                "bucket_server_side_encryption": bucket["bucket_server_side_encryption"],
                "bucket_replication_config": bucket["bucket_replication_config"]
            }

            rendered_template = template.render(context)

            output_file_path = f"{self.local_repo_path}/import-{bucket['bucket_name']}.tf"
            with open(output_file_path, "w") as f:
                f.write(rendered_template)

            Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan", f"-generate-config-out=generated-plan-import-{bucket['bucket_name']}.tf"], profile=self.aws_profile)

            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(input_tf_file=f"{self.local_repo_path}/generated-plan-import-{bucket['bucket_name']}.tf")

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
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "init"], profile=self.aws_profile)

        s3_bucket_details = self.describe_s3_buckets()
        self.generate_import_blocks(s3_bucket_details)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"], profile=self.aws_profile)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"], profile=self.aws_profile)