from utils.utilities import Utilities
from jinja2 import Environment, FileSystemLoader
from loguru import logger
import os
from botocore.exceptions import ClientError
from utils.cleanup import cleanup_tf_plan_file
import sys



class ALBImportSetUp:
    """
    Import Block for EC2 Import.
    Supoprted resources: EC2, EBS, Route53
    Note: Target Group Attachement resource import is not supported by Provider
    """

    def __init__(self, region, resource, local_repo_path, filters):
        self.client = Utilities.create_client(region=region, resource="elbv2")
        self.tmpl = Environment(loader=FileSystemLoader('templates'))
        self.region = region
        self.local_repo_path = local_repo_path
        self.tag_filters = {key: value for key, value in filters} if filters else {}
    
    
    def describe_load_balancers(self):
        """
        Get details for all ALBs and NLBs, filtered by tags
        """
        # Retrieve the list of load balancers
        load_balancers = self.client.describe_load_balancers()['LoadBalancers']
        
        lb_details_list = []

        # Iterate over all load balancers and retrieve their details
        for lb in load_balancers:
            lb_arn = lb['LoadBalancerArn']
            lb_type = lb['Type']

            # Retrieve tags for the load balancer
            lb_tags = self.client.describe_tags(ResourceArns=[lb_arn])['TagDescriptions'][0]['Tags']
            lb_tags_dict = {tag['Key']: tag['Value'] for tag in lb_tags}

            # Check if the load balancer matches the tag filters
            if all(lb_tags_dict.get(key) == value for key, value in self.tag_filters.items()):
                # Retrieve listeners for the load balancer
                listeners = self.client.describe_listeners(LoadBalancerArn=lb_arn)['Listeners']
                listener_details = []

                for listener in listeners:
                    listener_arn = listener['ListenerArn']
                    listener_port = listener['Port']
                    # Retrieve target groups for each listener
                    target_groups = self.client.describe_target_groups(LoadBalancerArn=lb_arn)['TargetGroups']
                    target_group_arns = [tg['TargetGroupArn'] for tg in target_groups]
                    
                    listener_detail = {
                        "listener_arn": listener_arn,
                        "listener_port": listener_port,
                        "target_groups": target_group_arns
                    }
                    listener_details.append(listener_detail)


                # Create the lb_details dictionary
                lb_details = {
                    "lb_arn": lb_arn,
                    "lb_name": lb['LoadBalancerName'],
                    "lb_type": lb_type,
                    "lb_listeners": listener_details,
                    "security_groups": lb.get('SecurityGroups', []),
                }
                lb_details_list.append(lb_details)

        return lb_details_list


    def generate_import_blocks(self, load_balancers):
        """
        Generate Import Blocks, Generate Terraform code, Cleanup Terraform code
        """
        if not load_balancers:
            logger.info("No ALB  found: Nothing to do. Exitting")
            sys.exit(1)

        template = self.tmpl.get_template('alb_import.tf.j2')

        for load_balancer in load_balancers:
            logger.info(f"Importing : {load_balancer}")
            
            context = {
                'load_balancer_arn': load_balancer['lb_arn'],
                'load_balancer_name': load_balancer['lb_name'],
                'load_balancer_listeners': load_balancer['lb_listeners'],
                'security_groups': load_balancer['security_groups'],
            }

            rendered_template = template.render(context)
            
            output_file_path = f"{self.local_repo_path}/import-{load_balancer['lb_name']}-{load_balancer['lb_type']}.tf"
            with open(output_file_path, 'w') as f:
                f.write(rendered_template)

            Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan", f"-generate-config-out=generated-plan-import-{load_balancer['lb_name']}-{load_balancer['lb_type']}.tf"])
            
            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(input_tf_file=f"{self.local_repo_path}/generated-plan-import-{load_balancer['lb_name']}-{load_balancer['lb_type']}.tf")
            
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
        
        load_balancers = self.describe_load_balancers()
        self.generate_import_blocks(load_balancers)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"])
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"])
