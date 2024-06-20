import boto3
import sys
import re

# Define mapping of resource types to AWS client methods and resource identifiers
RESOURCE_CONFIG = {
    'ec2': {'client': 'ec2', 'client_method': 'describe_instances', 'response_key': 'Reservations', 'resource_key': 'Instances', 'id_key': 'InstanceId', 'name_key': 'Name', 'terraform_resource_type': 'aws_instance'},
    'ebs': {'client': 'ec2', 'client_method': 'describe_volumes', 'response_key': 'Volumes', 'resource_key': None, 'id_key': 'VolumeId', 'name_key': 'Name', 'terraform_resource_type': 'aws_ebs_volume'},
    'ebs-attachments': {'client': 'ec2', 'client_method': 'describe_volumes', 'response_key': 'Volumes', 'resource_key': 'Attachments', 'id_key': 'VolumeId', 'name_key': 'VolumeId', 'terraform_resource_type': 'aws_volume_attachment'},
    'route53': {'client': 'route53', 'client_method': 'list_hosted_zones', 'response_key': 'HostedZones', 'resource_key': None, 'id_key': 'Id', 'name_key': 'Name', 'terraform_resource_type': 'aws_route53_zone'},
    'route53-records': {'client': 'route53', 'client_method': 'list_resource_record_sets', 'response_key': 'ResourceRecordSets', 'resource_key': None, 'id_key': 'Name', 'name_key': 'Name', 'terraform_resource_type': 'aws_route53_record'},
    'rds-instance': {'client': 'rds', 'client_method': 'describe_db_instances', 'response_key': 'DBInstances', 'resource_key': None, 'id_key': 'DBInstanceIdentifier', 'name_key': 'DBInstanceIdentifier', 'terraform_resource_type': 'aws_db_instance'},
    'rds-cluster-snapshot': {'client': 'rds', 'client_method': 'describe_db_cluster_snapshots', 'response_key': 'DBClusterSnapshots', 'resource_key': None, 'id_key': 'DBClusterSnapshotIdentifier', 'name_key': 'DBClusterSnapshotIdentifier', 'terraform_resource_type': 'aws_db_cluster_snapshot'},
    'rds-option-group': {'client': 'rds', 'client_method': 'describe_option_groups', 'response_key': 'OptionGroupsList', 'resource_key': None, 'id_key': 'OptionGroupName', 'name_key': 'OptionGroupName', 'terraform_resource_type': 'aws_db_option_group'},
    'rds-parameter-group': {'client': 'rds', 'client_method': 'describe_db_parameter_groups', 'response_key': 'DBParameterGroups', 'resource_key': None, 'id_key': 'DBParameterGroupName', 'name_key': 'DBParameterGroupName', 'terraform_resource_type': 'aws_db_parameter_group'},
    'rds-snapshot': {'client': 'rds', 'client_method': 'describe_db_snapshots', 'response_key': 'DBSnapshots', 'resource_key': None, 'id_key': 'DBSnapshotIdentifier', 'name_key': 'DBSnapshotIdentifier', 'terraform_resource_type': 'aws_db_snapshot'},
    'rds-subnet-group': {'client': 'rds', 'client_method': 'describe_db_subnet_groups', 'response_key': 'DBSubnetGroups', 'resource_key': None, 'id_key': 'DBSubnetGroupName', 'name_key': 'DBSubnetGroupName', 'terraform_resource_type': 'aws_db_subnet_group'},
    'rds-cluster': {'client': 'rds', 'client_method': 'describe_db_clusters', 'response_key': 'DBClusters', 'resource_key': None, 'id_key': 'DBClusterIdentifier', 'name_key': 'DBClusterIdentifier', 'terraform_resource_type': 'aws_rds_cluster'},
    'security-group': {'client': 'ec2', 'client_method': 'describe_security_groups', 'response_key': 'SecurityGroups', 'resource_key': None, 'id_key': 'GroupId', 'name_key': 'GroupId', 'terraform_resource_type': 'aws_security_group'},
    'iam-role': {'client': 'iam', 'client_method': 'list_roles', 'response_key': 'Roles', 'resource_key': None, 'id_key': 'RoleName', 'name_key': 'RoleName', 'terraform_resource_type': 'aws_iam_role'},
    'iam-policy': {'client': 'iam', 'client_method': 'list_policies', 'response_key': 'Policies', 'resource_key': None, 'id_key': 'Arn', 'name_key': 'PolicyName', 'terraform_resource_type': 'aws_iam_policy'},
    'eks-cluster': {'client': 'eks', 'client_method': 'list_clusters', 'response_key': 'clusters', 'resource_key': None, 'id_key': 'Name', 'name_key': 'Name', 'terraform_resource_type': 'aws_eks_cluster'},
    'eks-addon': {'client': 'eks', 'client_method': 'list_addons', 'response_key': 'addons', 'resource_key': None, 'id_key': 'AddonName', 'name_key': 'AddonName', 'terraform_resource_type': 'aws_eks_addon'},
    'launch-template': {'client': 'ec2', 'client_method': 'describe_launch_templates', 'response_key': 'LaunchTemplates', 'resource_key': None, 'id_key': 'LaunchTemplateId', 'name_key': 'LaunchTemplateName', 'terraform_resource_type': 'aws_launch_template'},
    'eks-node-group': {'client': 'eks', 'client_method': 'list_nodegroups', 'response_key': 'nodegroups', 'resource_key': None, 'id_key': 'NodegroupName', 'name_key': 'NodegroupName', 'terraform_resource_type': 'aws_eks_node_group'},
    'elb': {'client': 'elb', 'client_method': 'describe_load_balancers', 'response_key': 'LoadBalancerDescriptions', 'resource_key': None, 'id_key': 'LoadBalancerName', 'name_key': 'LoadBalancerName', 'terraform_resource_type': 'aws_elb'},
    'alb': {'client': 'elbv2', 'client_method': 'describe_load_balancers', 'response_key': 'LoadBalancers', 'resource_key': None, 'id_key': 'LoadBalancerArn', 'name_key': 'LoadBalancerName', 'terraform_resource_type': 'aws_alb'},
}

def apply_tag_filters(resources, include_tag_key, include_tag_value, exclude_tag_key, exclude_tag_value):
    filtered_resources = []
    for resource in resources:
        tags = {tag['Key']: tag['Value'] for tag in resource.get('resource', {}).get('Tags', [])}

        if include_tag_key and tags.get(include_tag_key) != include_tag_value:
            continue
        if exclude_tag_key and tags.get(exclude_tag_key) == exclude_tag_value:
            continue

        filtered_resources.append(resource)

    return filtered_resources


def list_resources(region, resource_type, include_tag_key=None, include_tag_value=None, exclude_tag_key=None, exclude_tag_value=None):
    resources = {}

    if resource_type == 'all-resources':
        for res_type, config in RESOURCE_CONFIG.items():
            resources[res_type] = []

            client = boto3.client(config['client'], region_name=region)
            if res_type == 'route53-records':
                # Fetch hosted zones first to get HostedZoneId
                hosted_zones_response = client.list_hosted_zones()
                hosted_zones = hosted_zones_response.get('HostedZones', [])

                for hosted_zone in hosted_zones:
                    hosted_zone_id = hosted_zone['Id'].split('/')[-1]
                    # Get resource record sets for each hosted zone
                    response = client.list_resource_record_sets(HostedZoneId=hosted_zone_id)
                    records = response.get('ResourceRecordSets', [])

                    # Append each record to resources[res_type]
                    for record in records:
                        record['HostedZoneId'] = hosted_zone_id  # Ensure HostedZoneId is included in each record
                        resources[res_type].append({'id': record['Name'], 'name': record['Name'], 'resource': record})
            elif res_type in ['eks-cluster', 'eks-addon', 'eks-node-group']:
                clusters = client.list_clusters()['clusters']
                for cluster in clusters:
                    if res_type == 'eks-cluster':
                        resources[res_type].append({'id': cluster, 'name': cluster})
                    elif res_type == 'eks-addon':
                        addons = client.list_addons(clusterName=cluster)['addons']
                        for addon in addons:
                            resources[res_type].append({'id': f"{cluster}:{addon}", 'name': f"{cluster}_{addon}"})
                    elif res_type == 'eks-node-group':
                        nodegroups = client.list_nodegroups(clusterName=cluster)['nodegroups']
                        for nodegroup in nodegroups:
                            resources[res_type].append({'id': f"{cluster}:{nodegroup}", 'name': f"{cluster}_{nodegroup}"})
            else:
                response = getattr(client, config['client_method'])()
                for index, item in enumerate(response.get(config['response_key'], []), start=1):
                    if config['resource_key']:
                        for resource in item.get(config['resource_key'], []):
                            id = resource[config['id_key']]
                            name = next((tag['Value'] for tag in resource.get('Tags', []) if tag['Key'] == config['name_key']), None)
                            if not name:
                                name = f"aws_{config['terraform_resource_type']}.key{index}"
                            resources[res_type].append({'id': id, 'name': name, 'resource': resource})
                    else:
                        id = item[config['id_key']]
                        name = next((tag['Value'] for tag in item.get('Tags', []) if tag['Key'] == config['name_key']), None)
                        if not name:
                            name = f"aws_{config['terraform_resource_type']}.key{index}"
                        resources[res_type].append({'id': id, 'name': name, 'resource': item})

    elif resource_type in RESOURCE_CONFIG:
        resources[resource_type] = []

        config = RESOURCE_CONFIG[resource_type]
        client = boto3.client(config['client'], region_name=region)

        if resource_type == 'route53-records':
            hosted_zones_response = client.list_hosted_zones()
            hosted_zones = hosted_zones_response.get('HostedZones', [])

            for hosted_zone in hosted_zones:
                hosted_zone_id = hosted_zone['Id'].split('/')[-1]
                response = client.list_resource_record_sets(HostedZoneId=hosted_zone_id)
                records = response.get('ResourceRecordSets', [])

                for record in records:
                    record['HostedZoneId'] = hosted_zone_id
                    resources[resource_type].append({'id': record['Name'], 'name': record['Name'], 'resource': record})
        elif resource_type in ['eks-cluster', 'eks-addon', 'eks-node-group']:
            clusters = client.list_clusters()['clusters']
            for cluster in clusters:
                if resource_type == 'eks-cluster':
                    resources[resource_type].append({'id': cluster, 'name': cluster})
                elif resource_type == 'eks-addon':
                    addons = client.list_addons(clusterName=cluster)['addons']
                    for addon in addons:
                        resources[resource_type].append({'id': f"{cluster}:{addon}", 'name': f"{cluster}_{addon}"})
                elif resource_type == 'eks-node-group':
                    nodegroups = client.list_nodegroups(clusterName=cluster)['nodegroups']
                    for nodegroup in nodegroups:
                        resources[resource_type].append({'id': f"{cluster}:{nodegroup}", 'name': f"{cluster}_{nodegroup}"})
        else:
            response = getattr(client, config['client_method'])()
            for index, item in enumerate(response.get(config['response_key'], []), start=1):
                if config['resource_key']:
                    for resource in item.get(config['resource_key'], []):
                        id = resource[config['id_key']]
                        name = next((tag['Value'] for tag in resource.get('Tags', []) if tag['Key'] == config['name_key']), None)
                        if not name:
                            name = f"aws_{config['terraform_resource_type']}.key{index}"
                        resources[resource_type].append({'id': id, 'name': name, 'resource': resource})
                else:
                    id = item[config['id_key']]
                    name = next((tag['Value'] for tag in item.get('Tags', []) if tag['Key'] == config['name_key']), None)
                    if not name:
                        name = f"aws_{config['terraform_resource_type']}.key{index}"
                    resources[resource_type].append({'id': id, 'name': name, 'resource': item})

    else:
        print(f"Unsupported resource type: {resource_type}")
        sys.exit(1)

    # Apply tag filters if provided
    for res_type in resources:
        resources[res_type] = apply_tag_filters(resources[res_type], include_tag_key, include_tag_value, exclude_tag_key, exclude_tag_value)

    return resources


def generate_import_block(resource_type, resources):
    terraform_resource_type = RESOURCE_CONFIG[resource_type]['terraform_resource_type']

    import_blocks = []
    name_counts = {}  # Dictionary to keep track of occurrences of each resource name

    for resource in resources:
        name = re.sub(r'[^a-zA-Z0-9_]', '_', resource['name'])
     
        
        if resource_type == 'ebs-attachments':
            if 'resource' in resource:
                attachment = resource['resource']
                device_name = attachment['Device']
                volume_id = resource['id']
                instance_id = attachment['InstanceId']
                id = f"{device_name}:{volume_id}:{instance_id}"
                import_block = f"""import {{
  to = {terraform_resource_type}.{name}
  id = "{id}"
}}"""
                import_blocks.append(import_block)
        elif resource_type == 'route53-records':
            hosted_zone_id = resource['resource']['HostedZoneId'].split('/')[-1]  # Remove the prefix
            record_name = resource['id']
            record_type = resource['resource']['Type']  # Lookup the 'Type' value
            if record_type not in ["SOA", "NS"]:  # Skip NS and SOA record type, These are generated by AWS by default
                id = f"{hosted_zone_id}_{record_name}_{record_type}"
                import_block = f"""import {{
  to = {terraform_resource_type}.{name}{record_type}
  id = "{id}"
}}"""
                import_blocks.append(import_block)
        elif resource_type == 'alb' or resource_type == 'elb':
            id = resource['resource']['LoadBalancerArn']
            import_block = f"""import {{
  to = {terraform_resource_type}.{name}
  id = "{id}"
}}"""
            import_blocks.append(import_block)
        elif resource_type == 'iam-policy':
            id = resource['resource']['Arn']
            if not id.startswith('arn:aws:iam::aws:policy/'): # Skip AWS Managed Policy
                import_block = f"""import {{
  to = {terraform_resource_type}.{name}
  id = "{id}"
}}"""
                import_blocks.append(import_block)
        else:
            id = resource['id'].split('/')[-1]  # Remove any prefix for other resources
            import_block = f"""import {{
  to = {terraform_resource_type}.{name}
  id = "{id}"
}}"""
            import_blocks.append(import_block)

    return "\n\n".join(import_blocks)


def print_usage():
    print("Usage: python aws-import.py <region> <resource_type> <output_tf_file> [--include-tag-key <tag_key> --include-tag-value <tag_value>] [--exclude-tag-key <tag_key> --exclude-tag-value <tag_value>]")
    print("Arguments:")
    print("  <region>                The AWS region where resources are located.")
    print("  <resource_type>         The type of AWS resource to import (e.g., ec2, rds, eks).")
    print("                          Use 'all-resources' to list all supported resource types.")
    print("  <output_tf_file>        The output file to write the Terraform import block.")
    print("  --include-tag-key       Optional: The tag key to filter resources to include.")
    print("  --include-tag-value     Optional: The tag value to filter resources to include.")
    print("  --exclude-tag-key       Optional: The tag key to filter resources to exclude.")
    print("  --exclude-tag-value     Optional: The tag value to filter resources to exclude.")
    print()

def main():
    if len(sys.argv) < 4:
        print("Error: Invalid number of arguments.")
        print_usage()
        sys.exit(1)

    region = sys.argv[1]
    resource_type = sys.argv[2]
    output_file = sys.argv[3]

    include_tag_key = None
    include_tag_value = None
    exclude_tag_key = None
    exclude_tag_value = None

    if '--include-tag-key' in sys.argv and '--include-tag-value' in sys.argv:
        include_tag_key_index = sys.argv.index('--include-tag-key') + 1
        include_tag_value_index = sys.argv.index('--include-tag-value') + 1
        if include_tag_key_index < len(sys.argv) and include_tag_value_index < len(sys.argv):
            include_tag_key = sys.argv[include_tag_key_index]
            include_tag_value = sys.argv[include_tag_value_index]

    if '--exclude-tag-key' in sys.argv and '--exclude-tag-value' in sys.argv:
        exclude_tag_key_index = sys.argv.index('--exclude-tag-key') + 1
        exclude_tag_value_index = sys.argv.index('--exclude-tag-value') + 1
        if exclude_tag_key_index < len(sys.argv) and exclude_tag_value_index < len(sys.argv):
            exclude_tag_key = sys.argv[exclude_tag_key_index]
            exclude_tag_value = sys.argv[exclude_tag_value_index]

    if resource_type == 'all-resources':
        resources = list_resources(region, resource_type, include_tag_key, include_tag_value, exclude_tag_key, exclude_tag_value)
        total_resources = sum(len(res_list) for res_list in resources.values())

        print(f"# Found {total_resources} resources in {region} for all supported types:")
        for res_type, res_list in resources.items():
            print(f"# {res_type.capitalize()} Resources:")
            for resource in res_list:
                print(f"# ID: {resource['id']}, Name: {resource['name']}")
            print()

        if not total_resources:
            print(f"No resources found for any supported types in {region}. Exiting.")
            return

        with open(output_file, 'w') as tf_file:
            for res_type, res_list in resources.items():
                import_block = generate_import_block(res_type, res_list)
                tf_file.write(import_block + '\n\n')

    else:
        resources = list_resources(region, resource_type, include_tag_key, include_tag_value, exclude_tag_key, exclude_tag_value)

        print(f"# Found resources for {resource_type} in {region}:")
        for resource in resources[resource_type]:
            print(f"# ID: {resource['id']}, Name: {resource['name']}")
        print()

        if not resources[resource_type]:
            print(f"No resources found for {resource_type} in {region}. Exiting.")
            return

        import_block = generate_import_block(resource_type, resources[resource_type])

        with open(output_file, 'w') as tf_file:
            tf_file.write(import_block)

if __name__ == "__main__":
    main()
