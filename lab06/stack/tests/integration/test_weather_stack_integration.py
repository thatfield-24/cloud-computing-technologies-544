"""Integration tests marked integration, run against deployed AWS stack."""
import json
import os
import socket
import urllib.error
import urllib.request
import boto3
import pytest

pytestmark = pytest.mark.integration


def test_target_groups_healthy():
    """Integration Test: Verify both Weather and Advisor Target Groups report healthy instances."""
    elbv2 = boto3.client("elbv2", region_name=os.environ.get("AWS_REGION"))

    for tg_key in ["WEATHER_TG_ARN", "ADVISOR_TG_ARN"]:
        tg_arn = os.environ.get(tg_key)
        health_resp = elbv2.describe_target_health(TargetGroupArn=tg_arn)
        states = [
            desc["TargetHealth"]["State"]
            for desc in health_resp.get("TargetHealthDescriptions", [])
        ]
        assert len(states) > 0
        assert all(state == "healthy" for state in states)



def test_weather_cache_miss_then_hit():
    """Integration Test: Verify /weather?zip=60616 called twice returns cache 'miss' then 'hit'."""
    alb_dns = os.environ.get("ALB_DNS_NAME")
    port = os.environ.get("WEATHER_LISTENER_PORT", "8080")
    url = f"http://{alb_dns}:{port}/weather?zip=60616"

    # Call 1: Miss
    req1 = urllib.request.urlopen(url, timeout=15)
    data1 = json.loads(req1.read().decode())
    assert req1.status == 200
    assert data1.get("cache") == "miss"

    # Call 2: Hit
    req2 = urllib.request.urlopen(url, timeout=10)
    data2 = json.loads(req2.read().decode())
    assert req2.status == 200
    assert data2.get("cache") == "hit"


def test_weather_history_endpoint():
    """Integration Test: Verify /history lists saved database lookups."""
    alb_dns = os.environ.get("ALB_DNS_NAME")
    port = os.environ.get("WEATHER_LISTENER_PORT", "8080")
    url = f"http://{alb_dns}:{port}/history"

    req = urllib.request.urlopen(url, timeout=10)
    data = json.loads(req.read().decode())
    assert req.status == 200
    assert data.get("count", 0) >= 1
    assert isinstance(data.get("lookups"), list)


def test_weather_bad_and_unknown_zip():
    """Integration Test: Verify bad zip returns HTTP 400 and unknown zip returns HTTP 404."""
    alb_dns = os.environ.get("ALB_DNS_NAME")
    port = os.environ.get("WEATHER_LISTENER_PORT", "8080")

    # Bad Zip
    with pytest.raises(urllib.error.HTTPError) as exc_400:
        urllib.request.urlopen(f"http://{alb_dns}:{port}/weather?zip=abc", timeout=10)
    assert exc_400.value.code == 400

    # Unknown Zip
    with pytest.raises(urllib.error.HTTPError) as exc_404:
        urllib.request.urlopen(f"http://{alb_dns}:{port}/weather?zip=00000", timeout=10)
    assert exc_404.value.code == 404


def test_advisor_tier_returns_advice():
    """Integration Test: Verify /advice endpoint returns clothing advice."""
    alb_dns = os.environ.get("ALB_DNS_NAME")
    port = os.environ.get("ADVISOR_LISTENER_PORT", "8081")
    url = f"http://{alb_dns}:{port}/advice?zip=60616"

    req = urllib.request.urlopen(url, timeout=20)
    data = json.loads(req.read().decode())
    assert req.status == 200
    assert len(data.get("advice", "")) > 0


def test_app_instances_reachable_only_through_alb():
    """Integration Test: Verify app instances are unreachable directly on port 3000 but accessible via ALB."""
    ec2 = boto3.client("ec2", region_name=os.environ.get("AWS_REGION"))
    alb_dns = os.environ.get("ALB_DNS_NAME")
    weather_port = os.environ.get("WEATHER_LISTENER_PORT", "8080")

    res = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": ["weather-app"]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )
    public_ip = res["Reservations"][0]["Instances"][0]["PublicIpAddress"]

    with pytest.raises((urllib.error.URLError, TimeoutError, socket.timeout)):
        urllib.request.urlopen(f"http://{public_ip}:3000/", timeout=3)

    alb_req = urllib.request.urlopen(f"http://{alb_dns}:{weather_port}/", timeout=10)
    assert alb_req.status == 200


def test_db_port_not_reachable_from_local_computer():
    """Integration Test: Verify PostgreSQL database port 5432 is not publicly reachable from local computer."""
    db_host = os.environ.get("DB_HOST")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    result = sock.connect_ex((db_host, 5432))
    sock.close()

    assert result != 0


def test_iam_simulate_principal_policy_least_privilege():
    """Integration Test: Verify iam.simulate_principal_policy reports each role allowed for its secret and implicitDeny for the other."""
    iam = boto3.client("iam", region_name=os.environ.get("AWS_REGION"))
    sts = boto3.client("sts", region_name=os.environ.get("AWS_REGION"))

    account_id = sts.get_caller_identity()["Account"]
    region = os.environ.get("AWS_REGION")

    db_param_arn = f"arn:aws:ssm:{region}:{account_id}:parameter{os.environ.get('DB_PASSWORD_PARAM')}"
    gemini_param_arn = f"arn:aws:ssm:{region}:{account_id}:parameter{os.environ.get('GEMINI_PARAM_NAME')}"

    weather_role_arn = iam.get_role(RoleName=os.environ.get("WEATHER_ROLE_NAME"))["Role"]["Arn"]
    advisor_role_arn = iam.get_role(RoleName=os.environ.get("ADVISOR_ROLE_NAME"))["Role"]["Arn"]

    w_db = iam.simulate_principal_policy(
        PolicySourceArn=weather_role_arn, ActionNames=["ssm:GetParameter"], ResourceArns=[db_param_arn]
    )["EvaluationResults"][0]["EvalDecision"]
    w_gemini = iam.simulate_principal_policy(
        PolicySourceArn=weather_role_arn, ActionNames=["ssm:GetParameter"], ResourceArns=[gemini_param_arn]
    )["EvaluationResults"][0]["EvalDecision"]

    assert w_db == "allowed"
    assert w_gemini == "implicitDeny"

    a_gemini = iam.simulate_principal_policy(
        PolicySourceArn=advisor_role_arn, ActionNames=["ssm:GetParameter"], ResourceArns=[gemini_param_arn]
    )["EvaluationResults"][0]["EvalDecision"]
    a_db = iam.simulate_principal_policy(
        PolicySourceArn=advisor_role_arn, ActionNames=["ssm:GetParameter"], ResourceArns=[db_param_arn]
    )["EvaluationResults"][0]["EvalDecision"]

    assert a_gemini == "allowed"
    assert a_db == "implicitDeny"