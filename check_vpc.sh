#!/bin/bash
VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query "Vpcs[0].VpcId" --output text --region us-east-2)
echo "$VPC_ID"

SUBNET_A=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=availability-zone,Values=us-east-2a" \
  --query "Subnets[0].SubnetId" --output text --region us-east-2)

SUBNET_B=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=availability-zone,Values=us-east-2b" \
  --query "Subnets[0].SubnetId" --output text --region us-east-2)

echo "us-east-2a subnet: $SUBNET_A"
echo "us-east-2b subnet: $SUBNET_B"