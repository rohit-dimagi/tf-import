import boto3
import os
from dotenv import load_dotenv
import subprocess
from loguru import logger
import sys
from jinja2 import Environment, FileSystemLoader
import os
from enum import Enum
from botocore.exceptions import NoCredentialsError, ProfileNotFound


class SkipTag(Enum):
    """
    SKip Resources Containg this tag
    """

    TF_IMPORTED = "true"


class Utilities:
    """
    Utilities for Imports
    """

    @staticmethod
    def create_session(region, resource, env_file_path=".env", profile=None):
        load_dotenv(dotenv_path=env_file_path)

        try:
            if profile:
                session = boto3.Session(profile_name=profile, region_name=region)
            else:
                # Get access key and secret key from environment variables
                access_key = os.getenv("AWS_ACCESS_KEY_ID")
                secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

                if not access_key or not secret_key:
                    raise NoCredentialsError

                # Create session with access key, secret key, and optional region
                session = boto3.Session(aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region)

            client = session.resource(resource)
            return client

        except ProfileNotFound:
            raise ProfileNotFound(f"The specified profile '{profile}' does not exist.")
        except NoCredentialsError:
            raise NoCredentialsError("AWS credentials not found. Please provide them via environment variables or a profile.")

    @staticmethod
    def create_client(region, resource, env_file_path=".env", profile=None):
        load_dotenv(dotenv_path=env_file_path)

        try:
            if profile:
                session = boto3.Session(profile_name=profile, region_name=region)
                client = session.client(resource)
            else:
                # Get access key and secret key from environment variables
                access_key = os.getenv("AWS_ACCESS_KEY_ID")
                secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

                if not access_key or not secret_key:
                    raise NoCredentialsError

                # Create client with access key, secret key, and optional region
                client = boto3.client(resource, aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region)

            return client

        except ProfileNotFound:
            raise ProfileNotFound(f"The specified profile '{profile}' does not exist.")
        except NoCredentialsError:
            raise NoCredentialsError("AWS credentials not found. Please provide them via environment variables or a profile.")

    def run_terraform_cmd(cmd, profile):
        print(cmd)
        try:
            env = os.environ.copy()
            env["AWS_PROFILE"] = profile
            completed_process = subprocess.run(cmd, text=True, capture_output=True, env=env)
            if completed_process.returncode == 0:
                logger.info(completed_process.stdout)
            else:
                logger.info(completed_process.stderr)
            return completed_process.stdout, completed_process.stderr
        except subprocess.CalledProcessError as e:
            logger.error(f"Error during terraform {cmd}: {e}")
            sys.exit(1)

    @staticmethod
    def generate_tf_provider(local_repo_path, region):
        output_file_path = f"{local_repo_path}/providers.tf"

        if os.path.exists(output_file_path):
            logger.info(f"File {output_file_path} already exists.")
            return
        logger.info(f"Creating providers.tf file inside {local_repo_path}")
        tmpl = Environment(loader=FileSystemLoader("templates"))
        template = tmpl.get_template("providers.tf.j2")
        context = {"cloud_provider_region": region}

        rendered_template = template.render(context)

        with open(output_file_path, "w") as f:
            f.write(rendered_template)
