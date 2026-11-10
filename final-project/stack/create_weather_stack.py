#!/usr/bin/env python3
import base64
import json
import os
import sys
import time
import boto3
from botocore.exceptions import ClientError

def load_env_file(filepath=".env"):
    """Reads key-value pairs from a file into os.environ if present."""
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip("'\"")

def ensure_role_and_profile(iam, role_name, profile_name, trust_policy):
    try:
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
        )
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"Role {role_name} exists, skipping.")
    except ClientError as e:
        if "EntityAlreadyExists" in str(e):
            print(f"Role {role_name} exists, skipping.")
        else:
            raise

    try:
        iam.create_instance_profile(InstanceProfileName=profile_name)
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"Profile {profile_name} exists, skipping.")
    except ClientError as e:
        if "EntityAlreadyExists" in str(e):
            print(f"Profile {profile_name} exists, skipping.")
        else:
            raise

    try:
        iam.add_role_to_instance_profile(
            InstanceProfileName=profile_name, RoleName=role_name
        )
    except ClientError:
        pass

def ensure_target_group(elbv2, name, vpc_id):
    tg_arn = None
    try:
        tgs = elbv2.describe_target_groups(Names=[name]).get("TargetGroups", [])
        if tgs:
            tg_arn = tgs[0]["TargetGroupArn"]
            print(f"Target group {name} already exists, skipping.", file=sys.stderr)
    except ClientError as e:
        if "TargetGroupNotFound" in str(e):
            tg_arn = None
        else:
            raise

    if not tg_arn:
        resp = elbv2.create_target_group(
            Name=name,
            Protocol="HTTP",
            Port=3000,
            VpcId=vpc_id,
            TargetType="instance",
            HealthCheckProtocol="HTTP",
            HealthCheckPath="/",
            HealthCheckIntervalSeconds=10,
            HealthCheckTimeoutSeconds=5,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=2,
        )
        tg_arn = resp["TargetGroups"][0]["TargetGroupArn"]

    return tg_arn

def ensure_listener(elbv2, alb_arn, port, tg_arn):
    listeners_resp = elbv2.describe_listeners(LoadBalancerArn=alb_arn)
    existing_ports = [l["Port"] for l in listeners_resp.get("Listeners", [])]

    if int(port) in existing_ports:
        print(f"Listener on port {port} already exists, skipping.")
    else:
        elbv2.create_listener(
            LoadBalancerArn=alb_arn,
            Protocol="HTTP",
            Port=int(port),
            DefaultActions=[{"Type": "forward", "TargetGroupArn": tg_arn}],
        )

def build_user_data(name, app_dir, extra_env, extra_setup, aws_region):
    app_js_path = os.path.join(app_dir, "app.js")
    pkg_json_path = os.path.join(app_dir, "package.json")

    with open(app_js_path, "rb") as f:
        app_js_b64 = base64.b64encode(f.read()).decode("utf-8")
    with open(pkg_json_path, "rb") as f:
        pkg_json_b64 = base64.b64encode(f.read()).decode("utf-8")

    user_data_script = f"""#!/bin/bash
dnf update -y
dnf install -y nodejs
mkdir -p /opt/app
{extra_setup}
echo "{app_js_b64}" | base64 -d > /opt/app/app.js
echo "{pkg_json_b64}" | base64 -d > /opt/app/package.json
cd /opt/app
npm install --omit=dev
cat > /etc/systemd/system/{name}.service << 'SERVICE'
[Unit]
Description={name} app
After=network.target
[Service]
Environment=PORT=3000
Environment=AWS_REGION={aws_region}
{extra_env}
WorkingDirectory=/opt/app
ExecStart=/usr/bin/node /opt/app/app.js
Restart=always
User=ec2-user
[Install]
WantedBy=multi-user.target
SERVICE
chown -R ec2-user:ec2-user /opt/app
systemctl daemon-reload
systemctl enable {name}.service
systemctl start {name}.service
"""
    filename = f"user-data-{name}.py"
    with open(filename, "w") as f:
        f.write(user_data_script)

    return user_data_script

def ensure_launch_template(
    ec2,
    lt_name,
    profile_name,
    user_data_content,
    tag,
    ami_id,
    instance_type,
    key_name,
    app_security_group_id,
):
    user_data_b64 = base64.b64encode(user_data_content.encode("utf-8")).decode(
        "utf-8"
    )

    lt_data = {
        "ImageId": ami_id,
        "InstanceType": instance_type,
        "KeyName": key_name,
        "SecurityGroupIds": [app_security_group_id],
        "IamInstanceProfile": {"Name": profile_name},
        "UserData": user_data_b64,
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": tag}],
            }
        ],
    }

    lt_exists = False
    try:
        ec2.describe_launch_templates(LaunchTemplateNames=[lt_name])
        lt_exists = True
    except ClientError as e:
        if "NotFound" in str(e) or "InvalidLaunchTemplateName" in str(e):
            lt_exists = False
        else:
            raise

    if lt_exists:
        print(f"Template {lt_name} exists, publishing a new version")
        ec2.create_launch_template_version(
            LaunchTemplateName=lt_name,
            SourceVersion="1",
            LaunchTemplateData=lt_data,
        )
    else:
        ec2.create_launch_template(
            LaunchTemplateName=lt_name, LaunchTemplateData=lt_data
        )

def ensure_asg(
    autoscaling, asg_name, lt_name, tg_arn, tag, subnet_a, subnet_b
):
    asgs = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[asg_name]
    ).get("AutoScalingGroups", [])

    if asgs:
        print(f"Auto Scaling Group {asg_name} already exists, skipping.")
    else:
        autoscaling.create_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            LaunchTemplate={"LaunchTemplateName": lt_name, "Version": "$Latest"},
            MinSize=1,
            MaxSize=1,
            DesiredCapacity=1,
            VPCZoneIdentifier=f"{subnet_a},{subnet_b}",
            TargetGroupARNs=[tg_arn],
            HealthCheckType="ELB",
            HealthCheckGracePeriod=120,
            Tags=[
                {
                    "ResourceId": asg_name,
                    "ResourceType": "auto-scaling-group",
                    "Key": "Name",
                    "Value": tag,
                    "PropagateAtLaunch": True,
                }
            ],
        )

def main():
    load_env_file(".env")

    aws_region = os.environ.get("AWS_REGION")
    az_a = os.environ.get("AZ_A")
    az_b = os.environ.get("AZ_B")
    gemini_param_name = os.environ.get("GEMINI_PARAM_NAME")
    db_password_param = os.environ.get("DB_PASSWORD_PARAM")
    weather_role_name = os.environ.get("WEATHER_ROLE_NAME")
    weather_profile_name = os.environ.get("WEATHER_PROFILE_NAME")
    advisor_role_name = os.environ.get("ADVISOR_ROLE_NAME")
    advisor_profile_name = os.environ.get("ADVISOR_PROFILE_NAME")
    alb_sg_name = os.environ.get("ALB_SG_NAME")
    app_security_group_id = os.environ.get("APP_SECURITY_GROUP_ID")
    weather_listener_port = os.environ.get("WEATHER_LISTENER_PORT")
    advisor_listener_port = os.environ.get("ADVISOR_LISTENER_PORT")
    weather_tg_name = os.environ.get("WEATHER_TG_NAME")
    advisor_tg_name = os.environ.get("ADVISOR_TG_NAME")
    alb_name = os.environ.get("ALB_NAME")
    contact_email = os.environ.get("CONTACT_EMAIL")
    db_name = os.environ.get("DB_NAME")
    db_user = os.environ.get("DB_USER")
    cache_seconds = os.environ.get("CACHE_SECONDS")
    gemini_model = os.environ.get("GEMINI_MODEL")
    key_cache_seconds = os.environ.get("KEY_CACHE_SECONDS")
    ami_id = os.environ.get("AMI_ID")
    instance_type = os.environ.get("INSTANCE_TYPE")
    key_name = os.environ.get("KEY_NAME")
    weather_lt_name = os.environ.get("WEATHER_LT_NAME")
    advisor_lt_name = os.environ.get("ADVISOR_LT_NAME")
    weather_asg_name = os.environ.get("WEATHER_ASG_NAME")
    advisor_asg_name = os.environ.get("ADVISOR_ASG_NAME")

    session_kwargs = {}
    if aws_region:
        session_kwargs["region_name"] = aws_region

    sts = boto3.client("sts", **session_kwargs)
    ec2 = boto3.client("ec2", **session_kwargs)
    elbv2 = boto3.client("elbv2", **session_kwargs)
    autoscaling = boto3.client("autoscaling", **session_kwargs)
    iam = boto3.client("iam", **session_kwargs)
    ssm = boto3.client("ssm", **session_kwargs)

    account_id = sts.get_caller_identity()["Account"]
    gemini_param_arn = (
        f"arn:aws:ssm:{aws_region}:{account_id}:parameter{gemini_param_name}"
    )
    db_password_arn = (
        f"arn:aws:ssm:{aws_region}:{account_id}:parameter{db_password_param}"
    )

    # == 1. Checking the Gemini key and the database ==
    print("== 1. Checking the Gemini key and the database ==")
    try:
        ssm.get_parameter(Name=gemini_param_name)
    except (ssm.exceptions.ParameterNotFound, ClientError):
        print(
            f"Parameter {gemini_param_name} was not found. Create it first (Part C of the lab)."
        )
        sys.exit(1)

    if not os.path.exists("db_outputs.env"):
        print(
            "db_outputs.env was not found. Run ./create_database.py first (Part E of the lab)."
        )
        sys.exit(1)

    load_env_file("db_outputs.env")
    db_host = os.environ.get("DB_HOST")

    # == 2. IAM roles and instance profiles ==
    print("== 2. IAM roles and instance profiles ==")
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }

    ensure_role_and_profile(
        iam, weather_role_name, weather_profile_name, trust_policy
    )
    ensure_role_and_profile(
        iam, advisor_role_name, advisor_profile_name, trust_policy
    )

    weather_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["ssm:GetParameter"],
                "Resource": db_password_arn,
            }
        ],
    }
    iam.put_role_policy(
        RoleName=weather_role_name,
        PolicyName=f"{weather_role_name}-policy",
        PolicyDocument=json.dumps(weather_policy),
    )

    advisor_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["ssm:GetParameter"],
                "Resource": gemini_param_arn,
            }
        ],
    }
    iam.put_role_policy(
        RoleName=advisor_role_name,
        PolicyName=f"{advisor_role_name}-policy",
        PolicyDocument=json.dumps(advisor_policy),
    )

    print("Waiting 15s for IAM propagation...")
    time.sleep(15)

    # == 3. Default VPC and subnets in both AZs ==
    print("== 3. Default VPC and subnets in both AZs ==")
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])[
        "Vpcs"
    ]
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

    # == 4. Security groups ==
    print("== 4. Security groups ==")
    alb_security_group_id = None
    try:
        sgs = ec2.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [alb_sg_name]},
                {"Name": "vpc-id", "Values": [vpc_id]},
            ]
        ).get("SecurityGroups", [])
        if sgs:
            alb_security_group_id = sgs[0]["GroupId"]
    except ClientError:
        alb_security_group_id = None

    if not alb_security_group_id:
        sg_resp = ec2.create_security_group(
            GroupName=alb_sg_name,
            Description="Allow inbound to the ALB on the app listener ports",
            VpcId=vpc_id,
        )
        alb_security_group_id = sg_resp["GroupId"]

        ec2.authorize_security_group_ingress(
            GroupId=alb_security_group_id,
            IpProtocol="tcp",
            FromPort=int(weather_listener_port),
            ToPort=int(weather_listener_port),
            CidrIp="0.0.0.0/0",
        )
        ec2.authorize_security_group_ingress(
            GroupId=alb_security_group_id,
            IpProtocol="tcp",
            FromPort=int(advisor_listener_port),
            ToPort=int(advisor_listener_port),
            CidrIp="0.0.0.0/0",
        )
    else:
        print("ALB security group already exists, skipping.")

    try:
        ec2.revoke_security_group_ingress(
            GroupId=app_security_group_id,
            IpProtocol="tcp",
            FromPort=3000,
            ToPort=3000,
            CidrIp="0.0.0.0/0",
        )
    except ClientError:
        pass

    try:
        ec2.authorize_security_group_ingress(
            GroupId=app_security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 3000,
                    "ToPort": 3000,
                    "UserIdGroupPairs": [{"GroupId": alb_security_group_id}],
                }
            ],
        )
    except ClientError:
        pass

    # == 5. Target groups and the load balancer (the ALB comes first this time) ==
    print(
        "== 5. Target groups and the load balancer (the ALB comes first this time) =="
    )
    weather_tg_arn = ensure_target_group(elbv2, weather_tg_name, vpc_id)
    advisor_tg_arn = ensure_target_group(elbv2, advisor_tg_name, vpc_id)

    alb_arn = None
    try:
        lbs = elbv2.describe_load_balancers(Names=[alb_name]).get(
            "LoadBalancers", []
        )
        if lbs:
            alb_arn = lbs[0]["LoadBalancerArn"]
            print(f"Load balancer {alb_name} already exists, skipping.")
    except ClientError as e:
        if "LoadBalancerNotFound" in str(e):
            alb_arn = None
        else:
            raise

    if not alb_arn:
        alb_resp = elbv2.create_load_balancer(
            Name=alb_name,
            Subnets=[subnet_a, subnet_b],
            SecurityGroups=[alb_security_group_id],
            Scheme="internet-facing",
            Type="application",
        )
        alb_arn = alb_resp["LoadBalancers"][0]["LoadBalancerArn"]
        print("Waiting for the ALB to become active...")
        waiter = elbv2.get_waiter("load_balancer_available")
        waiter.wait(LoadBalancerArns=[alb_arn])

    ensure_listener(elbv2, alb_arn, weather_listener_port, weather_tg_arn)
    ensure_listener(elbv2, alb_arn, advisor_listener_port, advisor_tg_arn)

    alb_info = elbv2.describe_load_balancers(LoadBalancerArns=[alb_arn])
    alb_dns_name = alb_info["LoadBalancers"][0]["DNSName"]

    # == 6. Launch templates (the advisor needs the ALB address to reach the weather tier) ==
    print(
        "== 6. Launch templates (the advisor needs the ALB address to reach the weather tier) =="
    )
    weather_env = f"""Environment="NWS_USER_AGENT=(itmo-444-544 weather lab, {contact_email})"
Environment=DB_HOST={db_host}
Environment=DB_NAME={db_name}
Environment=DB_USER={db_user}
Environment=DB_PASSWORD_PARAM={db_password_param}
Environment=CACHE_SECONDS={cache_seconds}"""

    weather_setup = """dnf install -y postgresql15
curl -sS -o /opt/app/rds-ca.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem"""

    advisor_env = f"""Environment=WEATHER_URL=http://{alb_dns_name}:{weather_listener_port}
Environment=GEMINI_KEY_PARAM={gemini_param_name}
Environment=GEMINI_MODEL={gemini_model}
Environment=KEY_CACHE_SECONDS={key_cache_seconds}"""

    weather_ud = build_user_data(
        "weather", "weather-app", weather_env, weather_setup, aws_region
    )
    advisor_ud = build_user_data(
        "advisor", "advisor-app", advisor_env, "", aws_region
    )

    ensure_launch_template(
        ec2,
        weather_lt_name,
        weather_profile_name,
        weather_ud,
        "weather-app",
        ami_id,
        instance_type,
        key_name,
        app_security_group_id,
    )
    ensure_launch_template(
        ec2,
        advisor_lt_name,
        advisor_profile_name,
        advisor_ud,
        "advisor-app",
        ami_id,
        instance_type,
        key_name,
        app_security_group_id,
    )

    # == 7. Auto Scaling Groups (these launch the instances) ==
    print("== 7. Auto Scaling Groups (these launch the instances) ==")
    ensure_asg(
        autoscaling,
        weather_asg_name,
        weather_lt_name,
        weather_tg_arn,
        "weather-app",
        subnet_a,
        subnet_b,
    )
    ensure_asg(
        autoscaling,
        advisor_asg_name,
        advisor_lt_name,
        advisor_tg_arn,
        "advisor-app",
        subnet_a,
        subnet_b,
    )

    with open("stack_outputs.env", "w") as f:
        f.write(f"VPC_ID={vpc_id}\n")
        f.write(f"SUBNET_A={subnet_a}\n")
        f.write(f"SUBNET_B={subnet_b}\n")
        f.write(f"ALB_SECURITY_GROUP_ID={alb_security_group_id}\n")
        f.write(f"ALB_ARN={alb_arn}\n")
        f.write(f"ALB_DNS_NAME={alb_dns_name}\n")
        f.write(f"WEATHER_TG_ARN={weather_tg_arn}\n")
        f.write(f"ADVISOR_TG_ARN={advisor_tg_arn}\n")

    # Clean up generated user data shell files
    for tmp_file in ["user-data-weather.py", "user-data-advisor.py"]:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except OSError:
                pass

    print()
    print(f"Done. ALB DNS name: {alb_dns_name}")
    print(
        f"Weather service: http://{alb_dns_name}:{weather_listener_port}/weather?zip=60616 (saved lookups: /history)"
    )
    print(f"Advisor page: http://{alb_dns_name}:{advisor_listener_port}/")
    print(
        "Give the target groups 2 to 3 minutes to report healthy (the first boot installs Node and your app)."
    )

if __name__ == "__main__":
    main()