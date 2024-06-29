import boto3
import os
from dotenv import load_dotenv
import subprocess
from loguru import logger
import sys
from jinja2 import Environment, FileSystemLoader
import os
import json

class Utilities:
    """
    Utilities for Imports
    """

    @staticmethod
    def create_session(region, resource, env_file_path=".env"):
        load_dotenv(dotenv_path=env_file_path)

        # Get access key and secret key from environment variables
        access_key = os.getenv('AWS_ACCESS_KEY_ID')
        secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

        # Create session with access key, secret key, and optional region
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        client = session.resource(resource)
        
        return client
    
    @staticmethod
    def create_client(region, resource, env_file_path=".env"):
        load_dotenv(dotenv_path=env_file_path)

        # Get access key and secret key from environment variables
        access_key = os.getenv('AWS_ACCESS_KEY_ID')
        secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

        # Create session with access key, secret key, and optional region
        client = boto3.client(
            resource,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        return client
    
    @staticmethod
    def run_terraform_cmd(cmd):
        print(cmd)
        try:
            completed_process = subprocess.run(
                cmd,
                text=True,
                capture_output=True
            )
            if completed_process.returncode == 0:
                logger.info(completed_process.stdout)
            else:
                logger.info(completed_process.stderr)
            return completed_process.stdout,completed_process.stderr
        except subprocess.CalledProcessError as e:
           logger.error(f"Error during terraform {cmd}: {e}")
           sys.exit(1)

    @staticmethod
    def generate_tf_provider(local_repo_path, region):
        output_file_path = f"{local_repo_path}/providers.tf"
        
        if os.path.exists(output_file_path):
            logger.info(f"File {output_file_path} already exists.")
            return
        
        tmpl = Environment(loader=FileSystemLoader('templates'))
        template = tmpl.get_template('providers.tf.j2')
        context = {
            'cloud_provider_region': region 
        }

        rendered_template = template.render(context)

        with open(output_file_path, 'w') as f:
            f.write(rendered_template)

    @staticmethod
    def generate_tf_backend(local_repo_path, tfe_hostname, tfe_org, tfe_workspace):
        output_file_path = f"{local_repo_path}/backend.tf"
        
        if os.path.exists(output_file_path):
            logger.info(f"File {output_file_path} already exists.")
            return
        
        tmpl = Environment(loader=FileSystemLoader('templates'))
        template = tmpl.get_template('backend.tf.j2')
        
        context = {
            "tfe_hostname": tfe_hostname,
            "tfe_org_name": tfe_org,
            "tfe_workspace_name": tfe_workspace
        }

        rendered_template = template.render(context)

        with open(output_file_path, 'w') as f:
            f.write(rendered_template)
    
