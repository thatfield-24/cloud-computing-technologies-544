#!/usr/bin/env python3
import os
import secrets
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
    az_a = os.environ.get("AZ_A")
    az_b = os.environ.get("AZ_B")
    db_sg_name = os.environ.get("DB_SG_NAME")
    app_security_group_id = os.environ.get("APP_SECURITY_GROUP_ID")
    db_subnet_group_name = os.environ.get("DB_SUBNET_GROUP_NAME")
    db_password_param = os.environ.get("DB_PASSWORD_PARAM")
    db_instance_id = os.environ.get("DB_INSTANCE_ID")
    db_user = os.environ.get("DB_USER")
    db_name = os.environ.get("DB_NAME")

    session_kwargs = {}
    if aws_region:
        session_kwargs["region_name"] = aws_region

    ec2 = boto3.client("ec2", **session_kwargs)
    rds = boto3.client("rds", **session_kwargs)
    ssm = boto3.client("ssm", **session_kwargs)

    # == 1. Default VPC and subnets in both AZs ==
    print("== 1. Default VPC and subnets in both AZs ==")
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
    vpc_id = vpcs[0]["VpcId"]

    subnets_a = ec2.describe_subnets(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "availability-zone", "Values": [az_a]},
        ]
    )["Subnets"]
    subnet_a = subnets_a[0]["SubnetId"]

    subnets_b = ec2.describe_subnets(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "availability-zone", "Values": [az_b]},
        ]
    )["Subnets"]
    subnet_b = subnets_b[0]["SubnetId"]

    # == 2. Database security group (port 5432, from the app security group only) ==
    print("== 2. Database security group (port 5432, from the app security group only) ==")
    db_security_group_id = None
    try:
        sgs = ec2.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [db_sg_name]},
                {"Name": "vpc-id", "Values": [vpc_id]},
            ]
        ).get("SecurityGroups", [])
        if sgs:
            db_security_group_id = sgs[0]["GroupId"]
    except ClientError:
        db_security_group_id = None

    if db_security_group_id:
        print("Database security group already exists, skipping.")
    else:
        sg_resp = ec2.create_security_group(
            GroupName=db_sg_name,
            Description="PostgreSQL access from the lab app instances only",
            VpcId=vpc_id,
        )
        db_security_group_id = sg_resp["GroupId"]

        ec2.authorize_security_group_ingress(
            GroupId=db_security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 5432,
                    "ToPort": 5432,
                    "UserIdGroupPairs": [{"GroupId": app_security_group_id}],
                }
            ],
        )

    # == 3. DB subnet group ==
    print("== 3. DB subnet group ==")
    try:
        rds.create_db_subnet_group(
            DBSubnetGroupName=db_subnet_group_name,
            DBSubnetGroupDescription="Lab subnets for the weather database",
            SubnetIds=[subnet_a, subnet_b],
        )
    except rds.exceptions.DBSubnetGroupAlreadyExistsFault:
        print("DB subnet group already exists, skipping.")
    except ClientError as e:
        if "AlreadyExists" in str(e):
            print("DB subnet group already exists, skipping.")
        else:
            raise

    # == 4. Database password (random, stored as a SecureString, never printed) ==
    print("== 4. Database password (random, stored as a SecureString, never printed) ==")
    try:
        ssm.get_parameter(Name=db_password_param)
        print("Password parameter already exists, keeping it.")
    except ssm.exceptions.ParameterNotFound:
        generated_password = secrets.token_hex(16)
        ssm.put_parameter(
            Name=db_password_param,
            Value=generated_password,
            Type="SecureString",
        )

    db_password = ssm.get_parameter(
        Name=db_password_param, WithDecryption=True
    )["Parameter"]["Value"]

    # == 5. The PostgreSQL instance (free tier size, no backups) ==
    print("== 5. The PostgreSQL instance (free tier size, no backups) ==")
    try:
        rds.describe_db_instances(DBInstanceIdentifier=db_instance_id)
        print(f"Database {db_instance_id} already exists, skipping.")
    except rds.exceptions.DBInstanceNotFoundFault:
        rds.create_db_instance(
            DBInstanceIdentifier=db_instance_id,
            DBInstanceClass="db.t4g.micro",
            Engine="postgres",
            AllocatedStorage=20,
            StorageType="gp2",
            MasterUsername=db_user,
            MasterUserPassword=db_password,
            DBName=db_name,
            DBSubnetGroupName=db_subnet_group_name,
            VpcSecurityGroupIds=[db_security_group_id],
            AvailabilityZone=az_a,
            BackupRetentionPeriod=0,
            MultiAZ=False,
            PubliclyAccessible=False,
            AutoMinorVersionUpgrade=False,
            DeletionProtection=False,
            StorageEncrypted=True,
        )

    del db_password

    print("Waiting for the database to become available (usually 5 to 10 minutes)...")
    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(
        DBInstanceIdentifier=db_instance_id,
        WaiterConfig={"Delay": 15, "MaxAttempts": 120},
    )

    db_info = rds.describe_db_instances(DBInstanceIdentifier=db_instance_id)
    db_host = db_info["DBInstances"][0]["Endpoint"]["Address"]

    with open("db_outputs.env", "w") as f:
        f.write(f"DB_HOST={db_host}\n")
        f.write(f"DB_SECURITY_GROUP_ID={db_security_group_id}\n")

    print()
    print(f"Done. Database endpoint: {db_host}")
    print("Automated backups are OFF (retention 0) and no final snapshot will be taken on delete.")
    print("Next: ./create_weather_stack.sh. When testing is finished: ./delete_weather_stack.sh then ./delete_database.sh")

if __name__ == "__main__":
    main()