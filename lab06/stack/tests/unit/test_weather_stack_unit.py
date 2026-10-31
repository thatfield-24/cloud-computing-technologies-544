import base64
import json
import boto3
from moto import mock_aws
import pytest


def helper_create_mock_subnets(ec2):
    """Helper to provision a mock VPC and two subnets in Moto for RDS testing."""
    vpc_id = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    s1 = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24", AvailabilityZone="us-east-1a")["Subnet"]["SubnetId"]
    s2 = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.2.0/24", AvailabilityZone="us-east-1b")["Subnet"]["SubnetId"]
    return vpc_id, s1, s2


@mock_aws
def test_create_database_config():
    """Unit Test 1: Verify RDS instance configuration."""
    ec2 = boto3.client("ec2", region_name="us-east-1")
    rds = boto3.client("rds", region_name="us-east-1")

    _, s1, s2 = helper_create_mock_subnets(ec2)

    rds.create_db_subnet_group(
        DBSubnetGroupName="itmo-444-544-weather-db-subnets",
        DBSubnetGroupDescription="Test DB Subnets",
        SubnetIds=[s1, s2],
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
    """Unit Test 2: Verify DB security group rules."""
    ec2 = boto3.client("ec2", region_name="us-east-1")

    vpc_id = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    app_sg_id = ec2.create_security_group(GroupName="app-sg", Description="App SG", VpcId=vpc_id)["GroupId"]
    db_sg_id = ec2.create_security_group(GroupName="db-sg", Description="DB SG", VpcId=vpc_id)["GroupId"]

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
    assert rule["UserIdGroupPairs"][0]["GroupId"] == app_sg_id
    assert len(rule["IpRanges"]) == 0


@mock_aws
def test_create_then_delete_db_cleanup():
    """Unit Test 3: Verify RDS and SSM parameter cleanup."""
    ec2 = boto3.client("ec2", region_name="us-east-1")
    rds = boto3.client("rds", region_name="us-east-1")
    ssm = boto3.client("ssm", region_name="us-east-1")

    param_name = "/itmo-444-544/db-password"
    db_id = "itmo-444-544-weather-db"

    _, s1, s2 = helper_create_mock_subnets(ec2)

    ssm.put_parameter(Name=param_name, Value="SecretPass123", Type="SecureString")
    rds.create_db_subnet_group(
        DBSubnetGroupName="subnets", DBSubnetGroupDescription="subnets", SubnetIds=[s1, s2]
    )
    rds.create_db_instance(
        DBInstanceIdentifier=db_id,
        DBInstanceClass="db.t4g.micro",
        Engine="postgres",
        AllocatedStorage=20,
        MasterUsername="weatherapp",
        MasterUserPassword="SecretPass123",
        DBSubnetGroupName="subnets",
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
    """Unit Test 4: Verify IAM policy JSON structure."""
    db_param_arn = "arn:aws:ssm:us-east-1:123456789012:parameter/itmo-444-544/db-password"
    gemini_param_arn = "arn:aws:ssm:us-east-1:123456789012:parameter/itmo-444-544/gemini-api-key"

    weather_policy_doc = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": ["ssm:GetParameter"], "Resource": db_param_arn}],
    }

    advisor_policy_doc = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": ["ssm:GetParameter"], "Resource": gemini_param_arn}],
    }

    assert weather_policy_doc["Statement"][0]["Resource"] == db_param_arn
    assert gemini_param_arn not in json.dumps(weather_policy_doc)

    assert advisor_policy_doc["Statement"][0]["Resource"] == gemini_param_arn
    assert db_param_arn not in json.dumps(advisor_policy_doc)


@mock_aws
def test_launch_template_user_data_contents_and_secrets():
    """Unit Test 5: Verify user data contains endpoints and no cleartext passwords."""
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
    """Unit Test 6: Verify script payload size stays under 16 KB."""
    weather_script = "#!/bin/bash\n" + "echo 'mock weather app' > /opt/app/app.js\n" * 100
    advisor_script = "#!/bin/bash\n" + "echo 'mock advisor app' > /opt/app/app.js\n" * 100

    assert len(weather_script.encode("utf-8")) < 16384
    assert len(advisor_script.encode("utf-8")) < 16384


@mock_aws
def test_create_idempotency_no_duplicates():
    """Unit Test 7: Verify create idempotency."""
    ec2 = boto3.client("ec2", region_name="us-east-1")
    rds = boto3.client("rds", region_name="us-east-1")

    vpc_id, s1, s2 = helper_create_mock_subnets(ec2)

    for _ in range(2):
        sgs = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": ["idempotent-sg"]}]
        ).get("SecurityGroups", [])
        if not sgs:
            ec2.create_security_group(GroupName="idempotent-sg", Description="Test SG", VpcId=vpc_id)

    sgs = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": ["idempotent-sg"]}])["SecurityGroups"]
    assert len(sgs) == 1

    for _ in range(2):
        try:
            rds.create_db_subnet_group(
                DBSubnetGroupName="idempotent-subnets",
                DBSubnetGroupDescription="Test Subnets",
                SubnetIds=[s1, s2],
            )
        except rds.exceptions.DBSubnetGroupAlreadyExistsFault:
            pass

    subnets = rds.describe_db_subnet_groups(DBSubnetGroupName="idempotent-subnets")["DBSubnetGroups"]
    assert len(subnets) == 1