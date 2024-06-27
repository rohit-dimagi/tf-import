from utils.utilities import Utilities
from jinja2 import Environment, FileSystemLoader
from loguru import logger
import os
from botocore.exceptions import ClientError
from utils.cleanup import cleanup_tf_plan_file
import sys



class EKSImportSetUp:
    """
    Import Block for EC2 Import.
    Supoprted resources: EC2, EBS, Route53
    Note: Target Group Attachement resource import is not supported by Provider
    """

    def __init__(self, region, resource, local_repo_path, filters):
        self.client = Utilities.create_client(region=region, resource=resource)
        self.tmpl = Environment(loader=FileSystemLoader('templates'))
        self.region = region
        self.local_repo_path = local_repo_path
        self.tag_filters = {key: value for key, value in filters} if filters else {}
    
    
    def describe_eks_cluster(self):
        """
        Get Instance details
        """
    
        cluster_names = self.client.list_clusters()['clusters']
        cluster_details = []
    
        for cluster_name in cluster_names:
            cluster = self.client.describe_cluster(name=cluster_name)['cluster']
            
            # Retrieve tags for the cluster
            cluster_tags = self.client.list_tags_for_resource(
                resourceArn=cluster['arn']
            )['tags']

            # Check if the cluster matches the tag filters
            if all(cluster_tags.get(key) == value for key, value in self.tag_filters.items()):
                # Retrieve node groups for the cluster
                node_group_names = self.client.list_nodegroups(clusterName=cluster_name)['nodegroups']
                node_groups = []

                for node_group_name in node_group_names:
                    node_group_info = self.client.describe_nodegroup(
                        clusterName=cluster_name,
                        nodegroupName=node_group_name
                    )['nodegroup']

                    # Retrieve the launch template ID if it exists
                    launch_template_id = node_group_info.get('launchTemplate', {}).get('id', "")
                    
                    # Retrieve the ASG names
                    asg_names = [asg['name'] for asg in node_group_info.get('resources', {}).get('autoScalingGroups', [])]

                    node_group_detail = {
                        "name": node_group_info['nodegroupName'],
                        "launch_template": launch_template_id,
                        "asg_names": asg_names
                    }
                    node_groups.append(node_group_detail)

                # Retrieve addons for the cluster
                addon_names = self.client.list_addons(clusterName=cluster_name).get('addons', [])
                addons = []
                for addon_name in addon_names:
                    addon_info = self.client.describe_addon(clusterName=cluster_name, addonName=addon_name)['addon']
                    addons.append(addon_info['addonName'])

                cluster_detail = {
                    "cluster_name": cluster['name'],
                    'eks_add_ons': addons,
                    'node_groups': node_groups,
                    "vpc_id": cluster['resourcesVpcConfig']['vpcId'],
                    "security_groups": cluster['resourcesVpcConfig']['securityGroupIds'],
                    "iam_role": cluster['roleArn'].split('/')[-1],
                }
                cluster_details.append(cluster_detail)

        return cluster_details


    def generate_import_blocks(self, eks_cluster_details):
        """
        Generate Import Blocks, Generate Terraform code, Cleanup Terraform code
        """
        if not eks_cluster_details:
            logger.info("No EKS Cluster found: Nothing to do. Exitting")
            sys.exit(1)

        template = self.tmpl.get_template('eks_import.tf.j2')

        for eks_cluster in eks_cluster_details:
            logger.info(f"Importing : {eks_cluster}")
            
            context = {
                'cluster_name': eks_cluster['cluster_name'],
                'eks_add_ons': eks_cluster['eks_add_ons'],
                'node_groups': eks_cluster['node_groups'],
            }

            rendered_template = template.render(context)
            
            output_file_path = f"{self.local_repo_path}/import-{eks_cluster['cluster_name']}.tf"
            with open(output_file_path, 'w') as f:
                f.write(rendered_template)

            Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan", f"-generate-config-out=generated-plan-import-{eks_cluster['cluster_name']}.tf"])
            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(input_tf_file=f"{self.local_repo_path}/generated-plan-import-{eks_cluster['cluster_name']}.tf")

        for filename in os.listdir(self.local_repo_path):
            if filename.endswith('.imported'):
                new_filename = filename.replace('.imported', '')
                old_file = os.path.join(self.local_repo_path, filename)
                new_file = os.path.join(self.local_repo_path, new_filename)
                os.rename(old_file, new_file)       

   
    def set_everything(self):
        """
        Setup the WorkFlow Steps.
        """
        Utilities.generate_tf_provider(self.local_repo_path, region=self.region)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "init"])
        
        eks_clusters = self.describe_eks_cluster()
        self.generate_import_blocks(eks_clusters)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"])
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"])
