#!/usr/bin/env python3
import argparse
from import_ec2 import EC2ImportSetUp
from import_rds import RDSImportSetUp
from import_eks import EKSImportSetUp
from import_alb import ALBImportSetUp

from loguru import logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TF Import Script")
    parser.add_argument("--resource", dest="resource", help="Resource Type ", type=str, required=True)
    parser.add_argument("--local-repo-path", dest="local_repo_path", help="Local Repo Path", type=str, required=True)
    parser.add_argument("--region", dest="region", help="AWS Region", type=str, required=True)
    parser.add_argument("--hosted-zone-name", dest="hosted_zone_name", help="AWS Route53 hosted Zone", type=str)
    parser.add_argument("-t", "--tag", action="append", nargs=2, metavar=("key", "value"), help="Specify a tag filter as key value pair, e.g. -t TF_MANAGED true -t env dev")
    args = parser.parse_args()

    if args.resource == "ec2" and not args.hosted_zone_name:
        parser.error("--hosted-zone-name is required when resource is 'ec2'")

    if args.resource == "ec2":
        ec2_import = EC2ImportSetUp(region=args.region, resource=args.resource, local_repo_path=args.local_repo_path, hosted_zone_name=args.hosted_zone_name, filters=args.tag)
        ec2_import.set_everything()

    elif args.resource == "rds":
        rds_import = RDSImportSetUp(region=args.region, resource=args.resource, local_repo_path=args.local_repo_path, filters=args.tag)
        rds_import.set_everything()

    elif args.resource == "eks":
        eks_import = EKSImportSetUp(region=args.region, resource=args.resource, local_repo_path=args.local_repo_path, filters=args.tag)
        eks_import.set_everything()

    elif args.resource == "alb":
        eks_import = ALBImportSetUp(region=args.region, resource=args.resource, local_repo_path=args.local_repo_path, filters=args.tag)
        eks_import.set_everything()

    else:
        logger.info(f"Import Not currently supported for {args.resource}")
