#!/usr/bin/env python3
import os
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

def main():
    load_env_file(".env")
    if os.path.exists("stack_outputs.env"):
        load_env_file("stack_outputs.env")

    # Environment variables
    aws_region = os.environ.get("AWS_REGION")
    weather_asg_name = os.environ.get("WEATHER_ASG_NAME")
    advisor_asg_name = os.environ.get("ADVISOR_ASG_NAME")
    alb_name = os.environ.get("ALB_NAME")
    weather_tg_name = os.environ.get("WEATHER_TG_NAME")
    advisor_tg_name = os.environ.get("ADVISOR_TG_NAME")
    alb_sg_name = os.environ.get("ALB_SG_NAME")
    app_security_group_id = os.environ.get("APP_SECURITY_GROUP_ID")
    weather_lt_name = os.environ.get("WEATHER_LT_NAME")
    advisor_lt_name = os.environ.get("ADVISOR_LT_NAME")
    weather_role_name = os.environ.get("WEATHER_ROLE_NAME")
    weather_profile_name = os.environ.get("WEATHER_PROFILE_NAME")
    advisor_role_name = os.environ.get("ADVISOR_ROLE_NAME")
    advisor_profile_name = os.environ.get("ADVISOR_PROFILE_NAME")

    session_kwargs = {}
    if aws_region:
        session_kwargs["region_name"] = aws_region

    ec2 = boto3.client("ec2", **session_kwargs)
    elbv2 = boto3.client("elbv2", **session_kwargs)
    autoscaling = boto3.client("autoscaling", **session_kwargs)
    iam = boto3.client("iam", **session_kwargs)

    # == Deleting Auto Scaling Groups (this also terminates their instances) ==
    print("== Deleting Auto Scaling Groups (this also terminates their instances) ==")
    for asg in [weather_asg_name, advisor_asg_name]:
        if not asg:
            continue
        try:
            autoscaling.delete_auto_scaling_group(
                AutoScalingGroupName=asg, ForceDelete=True
            )
        except ClientError:
            pass

    for asg in [weather_asg_name, advisor_asg_name]:
        if not asg:
            continue
        for _ in range(20):
            try:
                groups = autoscaling.describe_auto_scaling_groups(
                    AutoScalingGroupNames=[asg]
                ).get("AutoScalingGroups", [])
                if not groups:
                    print(f"{asg} deleted.")
                    break
            except ClientError:
                print(f"{asg} deleted.")
                break
            time.sleep(15)

    # == Deleting the load balancer and target groups ==
    print("== Deleting the load balancer and target groups ==")
    alb_arn = os.environ.get("ALB_ARN")
    if not alb_arn and alb_name:
        try:
            lbs = elbv2.describe_load_balancers(Names=[alb_name]).get(
                "LoadBalancers", []
            )
            if lbs:
                alb_arn = lbs[0]["LoadBalancerArn"]
        except ClientError:
            alb_arn = None

    if alb_arn:
        try:
            elbv2.delete_load_balancer(LoadBalancerArn=alb_arn)
            waiter = elbv2.get_waiter("load_balancers_deleted")
            waiter.wait(
                LoadBalancerArns=[alb_arn],
                WaiterConfig={"Delay": 15, "MaxAttempts": 40},
            )
        except ClientError:
            pass

    for tg_name in [weather_tg_name, advisor_tg_name]:
        if not tg_name:
            continue
        try:
            tgs = elbv2.describe_target_groups(Names=[tg_name]).get(
                "TargetGroups", []
            )
            if tgs:
                tg_arn = tgs[0]["TargetGroupArn"]
                elbv2.delete_target_group(TargetGroupArn=tg_arn)
        except ClientError:
            pass

    # == Restoring the app security group and deleting the ALB security group ==
    print("== Restoring the app security group and deleting the ALB security group ==")
    alb_sg_id = os.environ.get("ALB_SECURITY_GROUP_ID")
    try:
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])[
            "Vpcs"
        ]
        vpc_id = vpcs[0]["VpcId"]

        if not alb_sg_id and alb_sg_name:
            sgs = ec2.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [alb_sg_name]},
                    {"Name": "vpc-id", "Values": [vpc_id]},
                ]
            ).get("SecurityGroups", [])
            if sgs:
                alb_sg_id = sgs[0]["GroupId"]
    except ClientError:
        pass

    if alb_sg_id and app_security_group_id:
        try:
            ec2.revoke_security_group_ingress(
                GroupId=app_security_group_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 3000,
                        "ToPort": 3000,
                        "UserIdGroupPairs": [{"GroupId": alb_sg_id}],
                    }
                ],
            )
        except ClientError:
            pass

    if app_security_group_id:
        try:
            ec2.authorize_security_group_ingress(
                GroupId=app_security_group_id,
                IpProtocol="tcp",
                FromPort=3000,
                ToPort=3000,
                CidrIp="0.0.0.0/0",
            )
        except ClientError:
            pass

    if alb_sg_id:
        for _ in range(10):
            try:
                ec2.delete_security_group(GroupId=alb_sg_id)
                print("ALB security group deleted.")
                break
            except ClientError:
                print("ALB network interfaces still releasing, waiting 15s...")
                time.sleep(15)

    # == Deleting launch templates ==
    print("== Deleting launch templates ==")
    for lt_name in [weather_lt_name, advisor_lt_name]:
        if lt_name:
            try:
                ec2.delete_launch_template(LaunchTemplateName=lt_name)
            except ClientError:
                pass

    # == Removing IAM instance profiles and roles ==
    print("== Removing IAM instance profiles and roles ==")
    role_profile_pairs = [
        (weather_role_name, weather_profile_name),
        (advisor_role_name, advisor_profile_name),
    ]

    for role, profile in role_profile_pairs:
        if profile and role:
            try:
                iam.remove_role_from_instance_profile(
                    InstanceProfileName=profile, RoleName=role
                )
            except ClientError:
                pass

        if profile:
            try:
                iam.delete_instance_profile(InstanceProfileName=profile)
            except ClientError:
                pass

        if role:
            try:
                iam.delete_role_policy(
                    RoleName=role, PolicyName=f"{role}-policy"
                )
            except ClientError:
                pass

            try:
                iam.delete_role(RoleName=role)
            except ClientError:
                pass

    # Clean up outputs file
    if os.path.exists("stack_outputs.env"):
        try:
            os.remove("stack_outputs.env")
        except OSError:
            pass

    print(
        "Weather stack removed. Your Gemini API key parameter was left in place (the last step of the experiments shows how to delete it)."
    )

if __name__ == "__main__":
    main()