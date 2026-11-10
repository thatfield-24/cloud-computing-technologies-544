#!/usr/bin/env python3
import os
import time
import boto3
from botocore.exceptions import ClientError

def load_env_file(filepath=".env"):
    """Reads key-value pairs from .env into os.environ if present."""
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip("'\"")

def main():
    load_env_file()

    # Environment variables
    aws_region = os.environ.get("AWS_REGION")
    db_instance_id = os.environ.get("DB_INSTANCE_ID")
    db_subnet_group_name = os.environ.get("DB_SUBNET_GROUP_NAME")
    db_sg_name = os.environ.get("DB_SG_NAME")
    db_password_param = os.environ.get("DB_PASSWORD_PARAM")

    session_kwargs = {}
    if aws_region:
        session_kwargs["region_name"] = aws_region

    ec2 = boto3.client("ec2", **session_kwargs)
    rds = boto3.client("rds", **session_kwargs)
    ssm = boto3.client("ssm", **session_kwargs)

    # == Deleting the database (no final snapshot, no kept backups) ==
    print("== Deleting the database (no final snapshot, no kept backups) ==")
    db_exists = False
    try:
        rds.describe_db_instances(DBInstanceIdentifier=db_instance_id)
        db_exists = True
    except rds.exceptions.DBInstanceNotFoundFault:
        print(f"Database {db_instance_id} not found, nothing to delete.")
    except ClientError as e:
        if "DBInstanceNotFound" in str(e):
            print(f"Database {db_instance_id} not found, nothing to delete.")
        else:
            raise

    if db_exists:
        rds.delete_db_instance(
            DBInstanceIdentifier=db_instance_id,
            SkipFinalSnapshot=True,
            DeleteAutomatedBackups=True,
        )
        print("Waiting for the database to be deleted (a few minutes)...")
        waiter = rds.get_waiter("db_instance_deleted")
        waiter.wait(
            DBInstanceIdentifier=db_instance_id,
            WaiterConfig={"Delay": 15, "MaxAttempts": 120},
        )

    # == Deleting the DB subnet group ==
    print("== Deleting the DB subnet group ==")
    try:
        rds.delete_db_subnet_group(DBSubnetGroupName=db_subnet_group_name)
    except (rds.exceptions.DBSubnetGroupNotFoundFault, ClientError):
        pass

    # == Deleting the database security group ==
    print("== Deleting the database security group ==")
    try:
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
        vpc_id = vpcs[0]["VpcId"]

        sgs = ec2.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [db_sg_name]},
                {"Name": "vpc-id", "Values": [vpc_id]},
            ]
        ).get("SecurityGroups", [])

        if sgs:
            db_sg_id = sgs[0]["GroupId"]
            for i in range(10):
                try:
                    ec2.delete_security_group(GroupId=db_sg_id)
                    print("Database security group deleted.")
                    break
                except ClientError:
                    print("Still releasing, waiting 15s...")
                    time.sleep(15)
    except ClientError:
        pass

    # == Deleting the database password parameter ==
    print("== Deleting the database password parameter ==")
    try:
        ssm.delete_parameter(Name=db_password_param)
    except (ssm.exceptions.ParameterNotFound, ClientError):
        pass

    # Clean up local output env file if present
    if os.path.exists("db_outputs.env"):
        os.remove("db_outputs.env")

    print("Database removed. Run the checks in the last experiment step to confirm no snapshots or backups remain.")

if __name__ == "__main__":
    main()