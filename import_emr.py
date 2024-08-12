from utils.utilities import Utilities, SkipTag
from jinja2 import Environment, FileSystemLoader
from loguru import logger
import os
from utils.cleanup import cleanup_tf_plan_file
import sys
import warnings
warnings.filterwarnings('ignore', category=FutureWarning, module='botocore.client')

class EMRImportSetUp:
    """
    Import Block for EMR Import.
    """

    def __init__(self, region, resource, local_repo_path, filters, profile):
        self.client = Utilities.create_client(region=region, resource=resource, profile=profile)
        self.tmpl = Environment(loader=FileSystemLoader("templates"))
        self.region = region
        self.aws_profile = profile
        self.local_repo_path = local_repo_path
        self.tag_filters = {key: value for key, value in filters} if filters else {}

    def describe_emr_cluster(self):
        """
        Get EMR details
        """

        # Retrieve a list of clusters
        clusters = self.client.list_clusters()["Clusters"]
        cluster_details = []

        for cluster in clusters:
            cluster_id = cluster["Id"]
            cluster_info = self.client.describe_cluster(ClusterId=cluster_id)["Cluster"]

            # Retrieve tags from the cluster information
            cluster_tags = {tag['Key']: tag['Value'] for tag in cluster_info.get("Tags", [])}

            # Skip cluster if TF_IMPORTED tag is set to true
            if cluster_tags.get("TF_IMPORTED") == "true":
                logger.info(f"Skipping EMR Cluster {cluster_info['Name']} where TF_IMPORTED tag is set")
                continue

            # Check if the cluster matches the tag filters
            if all(cluster_tags.get(key) == value for key, value in self.tag_filters.items()):
                cluster_detail = {
                    "cluster_name": cluster_info["Name"],
                    "cluster_id": cluster_info["Id"],
                }
                cluster_details.append(cluster_detail)

        logger.info(f"Total EMR Clusters Found: {len(cluster_details)}")
        return cluster_details

    def generate_import_blocks(self, emr_cluster_details):
        """
        Generate Import Blocks, Generate Terraform code, Cleanup Terraform code
        """
        if not emr_cluster_details:
            logger.info("No EMR Cluster found: Nothing to do. Exitting")
            sys.exit(1)

        template = self.tmpl.get_template("emr_import.tf.j2")

        for emr_cluster in emr_cluster_details:
            logger.info(f"Importing : {emr_cluster}")

            context = {
                        "cluster_name": emr_cluster["cluster_name"],
                        "cluster_id": emr_cluster["cluster_id"],
                    }

            rendered_template = template.render(context)

            output_file_path = f"{self.local_repo_path}/import-{emr_cluster['cluster_name']}.tf"
            with open(output_file_path, "w") as f:
                f.write(rendered_template)

            Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan", f"-generate-config-out=generated-plan-import-{emr_cluster['cluster_name']}.tf"], profile=self.aws_profile)
            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(input_tf_file=f"{self.local_repo_path}/generated-plan-import-{emr_cluster['cluster_name']}.tf")

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

        emr_clusters = self.describe_emr_cluster()
        self.generate_import_blocks(emr_clusters)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"], profile=self.aws_profile)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"], profile=self.aws_profile)