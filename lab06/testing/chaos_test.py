#!/usr/bin/env python3
"""
Scenarios supported:
1. instance-kill: Terminates an InService instance in the Weather or Advisor Auto Scaling Group,
   verifies cross-tier behavior (e.g., Advisor returns 502 while Weather is down), measures
   recovery time, logs metrics to CSV, and checks against the recovery SLO.
2. db-cutoff: Revokes port 5432 access on the Database Security Group, confirms the Weather service
   degrades gracefully (HTTP 200 with cache='unavailable'), and restores the network rule.

Usage:
  python3 chaos_test.py --tier weather
  python3 chaos_test.py --tier advisor --slo-seconds 120
  python3 chaos_test.py --scenario db-cutoff

Both db_outputs.env & stack_outputs.env needing to be in the testing folder for this chaos test to run correctly.
"""
import argparse
import csv
import os
import sys
import time
import urllib.error
import urllib.request
import boto3
from botocore.exceptions import ClientError


def load_env(path: str) -> dict:
    values = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip("'\"")
    return values


def probe_once(url: str, timeout: float = 3.0) -> bool:
    """Returns True if the URL answers HTTP 200 within timeout."""
    try:
        req = urllib.request.urlopen(url, timeout=timeout)
        return req.status == 200
    except Exception:
        return False


def get_inservice_instance_id(asg_name: str, region: str) -> str:
    autoscaling = boto3.client("autoscaling", region_name=region)
    try:
        res = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        groups = res.get("AutoScalingGroups", [])
        if not groups:
            return ""
        for instance in groups[0].get("Instances", []):
            if instance.get("LifecycleState") == "InService":
                return instance.get("InstanceId", "")
    except ClientError as e:
        print(f"Error querying ASG {asg_name}: {e}")
    return ""


def terminate_instance_via_asg(instance_id: str, region: str):
    autoscaling = boto3.client("autoscaling", region_name=region)
    autoscaling.terminate_instance_in_auto_scaling_group(
        InstanceId=instance_id, ShouldDecrementDesiredCapacity=False
    )


def wait_for_state(
    url: str,
    want_up: bool,
    poll_interval: float = 2.0,
    max_wait: float = 600.0,
    log_rows: list = None,
    t0: float = None,
):
    """Polls an endpoint until it matches want_up status or max_wait is reached."""
    if t0 is None:
        t0 = time.monotonic()
    deadline = t0 + max_wait

    while time.monotonic() < deadline:
        elapsed = time.monotonic() - t0
        is_up = probe_once(url, timeout=poll_interval)
        if log_rows is not None:
            log_rows.append([round(elapsed, 2), is_up])

        if is_up == want_up:
            return elapsed

        time.sleep(poll_interval)

    return None


def run_db_cutoff_scenario(env: dict, region: str):
    """Executes Lab06 Step 7: Revokes DB SG rule, verifies graceful degradation, restores rule."""
    print("== Scenario: Database Network Cutoff ==")
    db_sg_id = env.get("DB_SECURITY_GROUP_ID")
    app_sg_id = env.get("APP_SECURITY_GROUP_ID")
    alb_dns = env.get("ALB_DNS_NAME")
    weather_port = env.get("WEATHER_LISTENER_PORT", "8080")

    if not db_sg_id or not app_sg_id or not alb_dns:
        sys.exit("Missing required environment variables (DB_SECURITY_GROUP_ID, APP_SECURITY_GROUP_ID, ALB_DNS_NAME).")

    ec2 = boto3.client("ec2", region_name=region)
    url = f"http://{alb_dns}:{weather_port}/weather?zip=60616"

    print("Revoking Database Security Group Ingress Rule (port 5432)...")
    try:
        ec2.revoke_security_group_ingress(
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
    except ClientError as e:
        print(f"Warning/Error revoking SG rule: {e}")

    try:
        print("Waiting 35s for database connection pool retry backoff...")
        time.sleep(35)

        print(f"Testing Weather endpoint: {url}")
        req = urllib.request.urlopen(url, timeout=15)
        body = req.read().decode()
        import json
        data = json.loads(body)

        cache_status = data.get("cache")
        print(f"HTTP Status: {req.status}, Cache Status: '{cache_status}'")

        if req.status == 200 and cache_status in ["unavailable", "disabled"]:
            print("PASS: Weather service degraded gracefully during DB outage.")
        else:
            print(f"FAIL: Unexpected response during DB outage: {data}")

    finally:
        print("Restoring Database Security Group Ingress Rule...")
        try:
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
            print("Database rule restored.")
        except ClientError as e:
            print(f"Error restoring SG rule: {e}")


def main():
    parser = argparse.ArgumentParser(description="Lab06 Chaos & Recovery Test Script")
    parser.add_argument("--scenario", choices=["instance-kill", "db-cutoff"], default="instance-kill")
    parser.add_argument("--tier", choices=["weather", "advisor"], default="weather")
    parser.add_argument("--slo-seconds", type=float, default=None)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--max-wait", type=float, default=600.0)
    args = parser.parse_args()

    # Load environment settings from standard locations
    env = {
        **load_env(".env"),
        **load_env(os.path.expanduser("~/.env")),
        **load_env("stack_outputs.env"),
        **load_env("db_outputs.env"),
    }

    region = env.get("AWS_REGION", "us-east-1")

    if args.scenario == "db-cutoff":
        run_db_cutoff_scenario(env, region)
        return

    # Instance-kill Scenario
    alb_dns = env.get("ALB_DNS_NAME")
    if not alb_dns:
        sys.exit("ALB_DNS_NAME not found — deploy your stack first.")

    slo_seconds = args.slo_seconds if args.slo_seconds is not None else float(env.get("RECOVERY_SLO_SECONDS", 180))

    if args.tier == "weather":
        port = env.get("WEATHER_LISTENER_PORT", "8080")
        asg_name = env.get("WEATHER_ASG_NAME")
        probe_url = f"http://{alb_dns}:{port}/weather?zip=60616"
    else:
        port = env.get("ADVISOR_LISTENER_PORT", "8081")
        asg_name = env.get("ADVISOR_ASG_NAME")
        probe_url = f"http://{alb_dns}:{port}/"

    print(f"Target: {args.tier} tier at {probe_url}")
    print("Confirming the endpoint is healthy before starting...")
    if not probe_once(probe_url):
        sys.exit("Endpoint is not responding — resolve stack health issues before running chaos test.")

    instance_id = get_inservice_instance_id(asg_name, region)
    if not instance_id:
        sys.exit(f"No InService instance found in ASG '{asg_name}'.")

    print(f"Terminating instance {instance_id} via Auto Scaling Group...")
    log_rows = []
    t0 = time.monotonic()
    terminate_instance_via_asg(instance_id, region)

    # Optional cross-tier validation during Weather outage
    if args.tier == "weather":
        advisor_port = env.get("ADVISOR_LISTENER_PORT", "8081")
        advisor_url = f"http://{alb_dns}:{advisor_port}/advice?zip=33161"
        time.sleep(3)
        try:
            urllib.request.urlopen(advisor_url, timeout=5)
            print("Notice: Advisor did not return an error immediately after instance termination.")
        except urllib.error.HTTPError as exc:
            print(f"Verified: Advisor returned HTTP {exc.code} during Weather outage (no hang/crash).")
        except Exception as exc:
            print(f"Advisor request exception during Weather outage: {exc}")

    print("Waiting for endpoint to go down...")
    down_at = wait_for_state(
        probe_url,
        want_up=False,
        poll_interval=args.poll_interval,
        max_wait=args.max_wait,
        log_rows=log_rows,
        t0=t0,
    )

    if down_at is None:
        print("Endpoint never went down within max-wait (ASG may have had a healthy standby or termination lagged).")

    print("Waiting for endpoint to recover (become healthy)...")
    recovered_at = wait_for_state(
        probe_url,
        want_up=True,
        poll_interval=args.poll_interval,
        max_wait=args.max_wait,
        log_rows=log_rows,
        t0=t0,
    )

    log_path = f"chaos_test_{args.tier}_{int(t0)}.csv"
    with open(log_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["elapsed_seconds", "is_up"])
        writer.writerows(log_rows)
    print(f"Poll metrics written to {log_path}")

    if recovered_at is None:
        print(f"FAIL: Endpoint did not recover within max-wait ({args.max_wait:.0f}s).")
        sys.exit(1)

    print(f"Recovery time: {recovered_at:.1f}s (SLO: {slo_seconds:.0f}s)")
    if recovered_at <= slo_seconds:
        print("PASS: Recovery time met the SLO.")
        sys.exit(0)
    else:
        print("FAIL: Recovery time exceeded the SLO.")
        sys.exit(1)


if __name__ == "__main__":
    main()