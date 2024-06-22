import re
import sys
from loguru import logger
import os
import subprocess

# Define the RESOURCE_CLEANUP dictionary with patterns properly escaped
RESOURCE_CLEANUP = {
    "global": [
        "null",
        "= {}"
    ],
    "aws_instance": [
        "= 0",
        "= \[\]",
        "ipv6_address_count",
    ],
    "rds-cluster": [
        "= 0",
        "= \[\]",
    ],
    "rds-instance": [
        "= 0",
        "= \[\]",
    ],
    "aws_route53_record": [
        "multivalue_answer_routing_policy",
        "= 0",
        "= \[\]",
    ],
    "aws_ebs_volume": [
        "= 0"
    ],
    "aws_eks_node_group": [
        "= 0",
        "= \[\]"
    ],
    "aws_security_group": [
        "name_prefix"
    ],
    "aws_launch_template": [
        "name_prefix",
        "= 0",
        "= \[\]",
    ],
}


def remove_global_lines(tf_file, list_to_cleanup):
    output_file = f"{tf_file}-global-cleanup.tf"
    logger.info(f"Removing lines containing following items: {list_to_cleanup}")
    
    with open(tf_file, "r") as readfile:
        lines = readfile.readlines()
        filtered_lines = []
        
        for line in lines:
            if any(element in line for element in list_to_cleanup):
                # If 'Condition' is in the line and '= {}' is one of the elements, do not remove it.
                # Special rule for aws_iam_role properties assume_role_policy of jsonencode block.
                if "= {}" in line and "Condition" in line:
                    filtered_lines.append(line)
                continue
            filtered_lines.append(line)
        with open(output_file, 'w') as write_file:
            write_file.writelines(filtered_lines)
        
    logger.info(f"Generated intermediate file to process: {output_file}")
    return output_file


def should_remove_line(line, resource_type, custom_pattern=[]):
    """
    Determine if a line should be removed based on the resource type and global patterns.
    """
    if not custom_pattern:
        patterns = RESOURCE_CLEANUP.get(resource_type, [])
    else: 
        patterns = custom_pattern 
    
    for pattern in patterns:
        if re.search(pattern, line):
            return True
    return False

def process_terraform_plan(input_file, output_file):
    with open(input_file, 'r') as file:
        lines = file.readlines()

    new_lines = []
    in_resource_block = False
    current_resource_type = None
    is_iops_set = False
    is_gp2_set = False
    
    for line in lines:
        # Check if the line starts a new resource block
        resource_block_match = re.match(r'\s*resource\s+"(\w+)"\s+"[^"]+"\s+{', line)
        if resource_block_match:
            in_resource_block = True
            current_resource_type = resource_block_match.group(1)
            
            new_lines.append(line)
            continue

        # Check if the line ends a resource block
        if in_resource_block and re.match(r'\s*}$\n#', line):
            in_resource_block = False
            current_resource_type = None
            new_lines.append(line)
            continue

        # Process lines within a resource block
        if in_resource_block and current_resource_type:
            if current_resource_type == "aws_ebs_volume": # EDGE case for removing iops when type is gp2
                if  "iops" in line:
                    is_iops_set = True
                    get_iops_line = line
                if "gp2" in line:
                    is_gp2_set = True
                if is_gp2_set and is_iops_set:
                    new_lines.remove(get_iops_line)
                    is_iops_set = False
                    is_gp2_set = False

            if should_remove_line(line, current_resource_type):
                continue
        new_lines.append(line)
        

    # Write the cleaned content to a new file
    with open(output_file, 'w') as new_file:
        new_file.writelines(new_lines)

    logger.info(f"Cleanup Resources with Patterns: {RESOURCE_CLEANUP}")
    
    if os.path.exists(input_file):
        os.remove(input_file)
    logger.info(f"Removing Intermediate generated file: {input_file} ")

    logger.info(f"Generated Cleaned up File: {output_file}")


def run_terraform_cmd(cmd):
        logger.info("Formatting terraform code")
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

def print_usage():
    print("Usage: python cleanup.py <input_tf_file> <output_tf_file>")
    print("  <input_tf_file>        The Input file to read the Terraform Plan.")
    print("  <output_tf_file>       The output file to write the Terraform cleaned plan.")

def main():
    if len(sys.argv) < 2:
        print("Error: Invalid number of arguments.")
        print_usage()
        sys.exit(1)
    input_tf_file = sys.argv[1]
    output_tf_file = sys.argv[2]

    # Process the Global defaults vaules
    level1_cleanup_file = remove_global_lines(input_tf_file, RESOURCE_CLEANUP["global"])
    
    # Process resource Specific Blocks
    process_terraform_plan(level1_cleanup_file, output_tf_file)
    
    # Format and validate terraform code
    run_terraform_cmd(["terraform", "fmt"])
if __name__ == "__main__":
    main()