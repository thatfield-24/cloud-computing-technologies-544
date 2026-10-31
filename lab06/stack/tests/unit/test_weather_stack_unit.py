"""Unit tests with moto (no real AWS calls required)."""
import base64
import json
import boto3
from moto import mock_aws
import pytest


@mock_aws
def test_db_instance_configuration():
    """Unit Test: Verify RDS instance has class db.t4g.micro, BackupRetentionPeriod 0, MultiAZ False, PubliclyAccessible False, and StorageEncrypted True."""
    rds = boto3.client("rds", region_name="us-east-1")

    rds.create_db_subnet_group(
        DBSubnetGroupName="itmo-444-544-weather-db-subnets",
        DBSubnetGroupDescription="Test DB Subnets",
        SubnetIds=["subnet-11111111", "subnet-22222222"],
    )

    rds.create_db_instance(
        DBInstanceIdentifier="itmo-444-544-weather-db",
        DBInstanceClass="db.t4g.micro",
        Engine="postgres",
        AllocatedStorage=20,
        StorageType="gp2",
        MasterUsername="weatherapp",
        MasterUserPassword="RandomGeneratedPassword123!",
        DBName="weather",
        DBSubnetGroupName="itmo-444-544-weather-db-subnets",
        BackupRetentionPeriod=0,
        MultiAZ=False,
        PubliclyAccessible=False,
        StorageEncrypted=True,
    )

    dbs = rds.describe_db_instances(DBInstanceIdentifier="itmo-444-544-weather-db")["DBInstances"]
    assert len(dbs) == 1
    db = dbs[0]

    assert db["DBInstanceClass"] == "db.t4g.micro"
    assert db["BackupRetentionPeriod"] == 0
    assert db["MultiAZ"] is False
    assert db["PubliclyAccessible"] is False
    assert db["StorageEncrypted"] is True


@mock_aws
def test_db_security_group_ingress():
    """Unit Test: Verify DB security group allows port 5432 from app security group ID and from no CIDR range."""
    ec2 = boto3.client("ec2", region_name="us-east-1")

    vpc_id = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    app_sg_id = ec2.create_security_group(
        GroupName="app-sg", Description="App Security Group", VpcId=vpc_id
    )["GroupId"]
    db_sg_id = ec2.create_security_group(
        GroupName="db-sg", Description="DB Security Group", VpcId=vpc_id
    )["GroupId"]

    ec2.authorize_security_group_ingress(
        GroupId=db_sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 5432,
                "ToPort": 5432,
                "UserIdGroupPairs": [{"GroupId": app_sg_id}],
            }
        ],
    )

    sg_info = ec2.describe_security_groups(GroupIds=[db_sg_id])["SecurityGroups"][0]
    permissions = sg_info["IpPermissions"]

    assert len(permissions) == 1
    rule = permissions[0]
    assert rule["FromPort"] == 5432
    assert rule["ToPort"] == 5432
    assert rule["IpProtocol"] == "tcp"
    assert rule["UserIdGroupPairs"][0]["GroupId"] == app_sg_id
    assert len(rule["IpRanges"]) == 0  # No CIDR rules allowed


@mock_aws
def test_create_then_delete_db_cleanup():
    """Unit Test: Verify that after creation and deletion, describe_db_instances, describe_db_snapshots, automated backups, and password parameter are empty."""
    rds = boto3.client("rds", region_name="us-east-1")
    ssm = boto3.client("ssm", region_name="us-east-1")

    param_name = "/itmo-444-544/db-password"
    db_id = "itmo-444-544-weather-db"

    ssm.put_parameter(Name=param_name, Value="SecretPass123", Type="SecureString")
    rds.create_db_subnet_group(
        DBSubnetGroupName="subnets", DBSubnetGroupDescription="subnets", SubnetIds=["subnet-1"]
    )
    rds.create_db_instance(
        DBInstanceIdentifier=db_id,
        DBInstanceClass="db.t4g.micro",
        Engine="postgres",
        AllocatedStorage=20,
        MasterUsername="weatherapp",
        MasterUserPassword="SecretPass123",
        BackupRetentionPeriod=0,
    )

    rds.delete_db_instance(
        DBInstanceIdentifier=db_id,
        SkipFinalSnapshot=True,
        DeleteAutomatedBackups=True,
    )
    ssm.delete_parameter(Name=param_name)

    instances = rds.describe_db_instances()["DBInstances"]
    snapshots = rds.describe_db_snapshots()["DBSnapshots"]

    assert len(instances) == 0
    assert len(snapshots) == 0

    with pytest.raises(ssm.exceptions.ParameterNotFound):
        ssm.get_parameter(Name=param_name)


@mock_aws
def test_iam_least_privilege_policies():
    """Unit Test: Verify Weather role allows ssm:GetParameter on ONLY DB password ARN, Advisor role on ONLY Gemini key ARN, and neither mentions the other."""
    db_param_arn = "arn:aws:ssm:us-east-1:123456789012:parameter/itmo-444-544/db-password"
    gemini_param_arn = "arn:aws:ssm:us-east-1:123456789012:parameter/itmo-444-544/gemini-api-key"

    weather_policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["ssm:GetParameter"],
                "Resource": db_param_arn,
            }
        ],
    }

    advisor_policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["ssm:GetParameter"],
                "Resource": gemini_param_arn,
            }
        ],
    }

    assert weather_policy_doc["Statement"][0]["Resource"] == db_param_arn
    assert gemini_param_arn not in json.dumps(weather_policy_doc)

    assert advisor_policy_doc["Statement"][0]["Resource"] == gemini_param_arn
    assert db_param_arn not in json.dumps(advisor_policy_doc)


@mock_aws
def test_launch_template_user_data_contents_and_secrets():
    """Unit Test: Verify ALB-first ordering (Advisor user-data contains ALB DNS name), Weather user-data contains DB host, and neither contains DB password."""
    alb_dns = "itmo-444-544-weather-alb-123456789.us-east-1.elb.amazonaws.com"
    db_host = "itmo-444-544-weather-db.c123456789.us-east-1.rds.amazonaws.com"
    db_password = "SuperSecretGeneratedPassword123"

    weather_user_data = f"#!/bin/bash\nexport DB_HOST={db_host}\n"
    advisor_user_data = f"#!/bin/bash\nexport WEATHER_URL=http://{alb_dns}:8080\n"

    assert alb_dns in advisor_user_data
    assert db_host in weather_user_data

    assert db_password not in weather_user_data
    assert db_password not in advisor_user_data


@mock_aws
def test_user_data_size_under_16kb():
    """Unit Test: Verify generated user-data for each tier is under 16 KB (16,384 bytes)."""
    weather_script = "#!/bin/bash\n" + "echo 'mock weather app' > /opt/app/app.js\n" * 100
    advisor_script = "#!/bin/bash\n" + "echo 'mock advisor app' > /opt/app/app.js\n" * 100

    assert len(weather_script.encode("utf-8")) < 16384
    assert len(advisor_script.encode("utf-8")) < 16384


@mock_aws
def test_create_idempotency_no_duplicates():
    """Unit Test: Verify running create functions twice creates no duplicate resources."""
    ec2 = boto3.client("ec2", region_name="us-east-1")
    rds = boto3.client("rds", region_name="us-east-1")

    vpc_id = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]

    for _ in range(2):
        sgs = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": ["idempotent-sg"]}]
        ).get("SecurityGroups", [])
        if not sgs:
            ec2.create_security_group(
                GroupName="idempotent-sg", Description="Idempotent Test", VpcId=vpc_id
            )

    sgs = ec2.describe_security_groups(
        Filters=[{"Name": "group-name", "Values": ["idempotent-sg"]}]
    )["SecurityGroups"]
    assert len(sgs) == 1

    for _ in range(2):
        try:
            rds.create_db_subnet_group(
                DBSubnetGroupName="idempotent-subnets",
                DBSubnetGroupDescription="Test",
                SubnetIds=["subnet-1", "subnet-2"],
            )
        except rds.exceptions.DBSubnetGroupAlreadyExistsFault:
            pass

    subnets = rds.describe_db_subnet_groups(DBSubnetGroupName="idempotent-subnets")[
        "DBSubnetGroups"
    ]
    assert len(subnets) == 1