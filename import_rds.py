from utils.utilities import Utilities
from jinja2 import Environment, FileSystemLoader
from loguru import logger
import sys
import os
from utils.cleanup import cleanup_tf_plan_file

class RDSImportSetUp:
    """
    RDS instance import 
    """

    def __init__(self, environment, workspace, region, resource, local_repo_path, filters):
        self.client = Utilities.create_client(region=region, resource=resource)
        self.tmpl = Environment(loader=FileSystemLoader('templates'))
        self.region = region
        self.local_repo_path = local_repo_path
        self.resource_name = f"{environment}_{region}_rds_"
        self.workspace = workspace
        self.tag_filters = {key: value for key, value in filters} if filters else {}

    
    def get_rds_instances(self):
        """Retrieve all RDS instances."""
        
        instances = []
        paginator = self.client.get_paginator('describe_db_instances')
        for page in paginator.paginate():
            for db_instance in page['DBInstances']:
                db_instance_arn = db_instance['DBInstanceArn']
                # Get tags for the instance
                tags_response = self.client.list_tags_for_resource(ResourceName=db_instance_arn)
                tags = {tag['Key']: tag['Value'] for tag in tags_response['TagList']}
                
                # Check if the instance matches all tag filters:
                if 'DBClusterIdentifier' not in db_instance:
                    if all(tags.get(key) == value for key, value in self.tag_filters.items()):
                        instance_info = {
                            "identifier": db_instance['DBInstanceIdentifier'],
                            "is_aurora": "true" if db_instance['Engine'].startswith('aurora') else "false",
                            "parameter-group": db_instance['DBParameterGroups'][0]['DBParameterGroupName']
                        }
                        instances.append(instance_info) 
        return instances
    
    def get_rds_clusters(self):
        """Retrieve all RDS clusters."""
        
        clusters = []
        paginator = self.client.get_paginator('describe_db_clusters')
        for page in paginator.paginate():
            for db_cluster in page['DBClusters']:
                db_cluster_arn = db_cluster['DBClusterArn']
                
                # Get tags for the instance
                tags_response = self.client.list_tags_for_resource(ResourceName=db_cluster_arn)
                tags = {tag['Key']: tag['Value'] for tag in tags_response['TagList']}
                
                # Check if the instance matches all tag filters
                if all(tags.get(key) == value for key, value in self.tag_filters.items()):
                    security_groups = [sg['VpcSecurityGroupId'] for sg in db_cluster['VpcSecurityGroups']]
                    
                    # Get cluster instances and their parameter groups
                    cluster_instances = []
                    for instance_identifier in db_cluster['DBClusterMembers']:
                        instance_info = self.client.describe_db_instances(DBInstanceIdentifier=instance_identifier['DBInstanceIdentifier'])
                        for instance in instance_info['DBInstances']:
                            instance_data = {
                                "instance_identifier": instance['DBInstanceIdentifier'],
                                "db_parameter_group": [param_group['DBParameterGroupName'] for param_group in instance['DBParameterGroups']]
                            }
                            cluster_instances.append(instance_data)
                    
                    cluster_info = {
                        "kms_key_id": db_cluster['KmsKeyId'].split('/')[-1],
                        "identifier": db_cluster['DBClusterIdentifier'],
                        "is_aurora": "true" if db_cluster['Engine'].startswith('aurora') else "false",
                        "cluster_parameter": db_cluster['DBClusterParameterGroup'],
                        "security_groups": security_groups,
                        "cluster_instances": cluster_instances
                    }
                clusters.append(cluster_info)

        return clusters

    def generate_import_blocks(self, instances=[], clusters=[]):         
        if not clusters:
            logger.info("No Cluster found: Nothing to do. Exitting")
            sys.exit(1)       
        
        template = self.tmpl.get_template('rds_import.tf.j2')

        for cluster in clusters:
            logger.info(f"Importing : {cluster}")
            output_file_path = f"{self.local_repo_path}/imports_{cluster['identifier']}.tf"
            context = {
                'rds_cluster_identifier': cluster["identifier"],
                'cluster_parameter': cluster["cluster_parameter"],
                'cluster_instances': cluster['cluster_instances'],
                "kms_key_id": cluster["kms_key_id"],
                "security_groups": cluster["security_groups"],
                'is_cluster': "true"
            }

            rendered_template = template.render(context)

            with open(output_file_path, 'w') as f:
                f.write(rendered_template)
            
            Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan", f"-generate-config-out=generated-plan-import-{cluster['identifier']}.tf"])
            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(input_tf_file=f"{self.local_repo_path}/generated-plan-import-{cluster['identifier']}.tf")

        for filename in os.listdir(self.local_repo_path):
            if filename.endswith('.imported'):
                new_filename = filename.replace('.imported', '')
                old_file = os.path.join(self.local_repo_path, filename)
                new_file = os.path.join(self.local_repo_path, new_filename)
                os.rename(old_file, new_file)       
    

    def set_everything(self):
        Utilities.generate_tf_provider(self.local_repo_path, region=self.region)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "init"])
        clusters = self.get_rds_clusters()
        
        self.generate_import_blocks(clusters=clusters)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"])
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"])
    