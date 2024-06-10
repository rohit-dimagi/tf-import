from utils.utilities import Utilities
from jinja2 import Environment, FileSystemLoader
from loguru import logger

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
                    cluster_info = {
                        "identifier": db_cluster['DBClusterIdentifier'],
                        "is_aurora": "true" if db_cluster['Engine'].startswith('aurora') else "false",
                        "parameter-group": db_cluster['DBClusterParameterGroup']
                    }
                    clusters.append(cluster_info) 
        return clusters
    
    def generate_import_blocks(self, instances, clusters):        
        for instnace in instances:
            output_file_path = f"{self.local_repo_path}/imports_{instnace['identifier']}.tf"
            template = self.tmpl.get_template('rds_import.tf.j2')

            context = {
                'rds_identifier': instnace["identifier"],
                'db_param_group': instnace["parameter-group"],
                'is_cluster': "false"
            }

            rendered_template = template.render(context)

            with open(output_file_path, 'w') as f:
                f.write(rendered_template)
        
        for instnace in clusters:
            output_file_path = f"{self.local_repo_path}/imports_{instnace['identifier']}.tf"
            template = self.tmpl.get_template('rds_import.tf.j2')

            context = {
                'rds_identifier': instnace["identifier"],
                'db_param_group': instnace["parameter-group"],
                'is_cluster': "true"
            }

            rendered_template = template.render(context)

            with open(output_file_path, 'w') as f:
                f.write(rendered_template)
    

    def set_everything(self):
        clusters = self.get_rds_clusters()
        instances = self.get_rds_instances()
        logger.info(f"Instances: {instances}")
        logger.info(f"Instances: {clusters}")
        #self.generate_import_blocks(instances, clusters)

        #Utilities.generate_tf_backend(self.local_repo_path,tfe_hostname="app.terraform.io", tfe_workspace="store-api-iac", tfe_org="rohit-kumar-hcp")
        #Utilities.generate_tf_provider(self.local_repo_path, region=self.region)
        #Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "init"])
        #Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan", f"-generate-config-out={self.resource_name}.tf"])
        Utilities.clean_generated_tf_code(resource="rds", tf_file=f"{self.local_repo_path}/{self.resource_name}.tf")
        # with open(f"{self.local_repo_path}/{self.resource_name}.tf", "r+") as f:
        #     d = f.readlines()
        #     f.seek(0)
        #     for i in d:
        #         if "= 0" not in i:
        #             f.write(i)
        #         elif "null" not in i:
        #             f.write(i)
        #     f.truncate()
        # Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"])
