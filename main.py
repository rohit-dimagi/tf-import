#!/usr/bin/env python3
import argparse
from import_ec2 import EC2ImportSetUp
from import_rds import RDSImportSetUp

from loguru import logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TF Import Script")
    parser.add_argument("--env", dest="env",
                        help="AWS Environment name ", type=str, required=True)
    parser.add_argument("--workspace", dest="workspace",
                        help="TFE Workspace Name ", type=str, required=True)
    parser.add_argument("--resource", dest="resource",
                        help="Resource Type ", type=str, required=True)
    parser.add_argument("--local-repo-path", dest="local_repo_path",
                        help="Local Repo Path", type=str, required=True)
    parser.add_argument("--region", dest="region",
                        help="AWS Region", type=str, required=True)
    parser.add_argument("--hosted-zone-name", dest="hosted_zone_name",
                        help="AWS Route53 hosted Zone", type=str, required=True)
    parser.add_argument('-t', '--tag', action='append', nargs=2, metavar=('key', 'value'),
                        help='Specify a tag filter as key value pair, e.g. -t TF_MANAGED true -t env dev')
    args = parser.parse_args()

    
    test = EC2ImportSetUp(
                    region=args.region,
                    environment=args.env,
                    resource=args.resource,
                    workspace=args.workspace,
                    local_repo_path=args.local_repo_path,
                    hosted_zone_name=args.hosted_zone_name,
                    filters=args.tag
                    )
    test.set_everything()
    