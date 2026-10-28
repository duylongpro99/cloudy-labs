#!/usr/bin/env bash
# Deletes the Lab 6 + 7 resources recorded in out/<backend>/ids.json, in dependency order,
# and prints the wall-clock time. Usage: ./reset-by-api.sh <backend> <endpoint-url>
set -uo pipefail
BACKEND=${1:?backend}; ENDPOINT=${2:?endpoint}
IDS="$(dirname "$0")/out/$BACKEND/ids.json"
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
id() { python3 -c "import json,sys;v=json.load(open('$IDS'))$1;print(' '.join(v) if isinstance(v,list) else v)"; }
a() { aws --endpoint-url "$ENDPOINT" ec2 "$@" >/dev/null 2>>"$(dirname "$0")/out/$BACKEND/reset.err" || echo "  failed: ec2 $1" >&2; }
T0=$(python3 -c 'import time;print(time.time())')
a terminate-instances --instance-ids "$(id '["instance"]')"
aws --endpoint-url "$ENDPOINT" ec2 wait instance-terminated --instance-ids "$(id '["instance"]')"
a delete-key-pair --key-name lab07-key
a delete-security-group --group-id "$(id '["sg"]')"
for rt in "$(id '["rt_public"]')" "$(id '["rt_private"]')"; do
  for assoc in $(aws --endpoint-url "$ENDPOINT" ec2 describe-route-tables --route-table-ids "$rt" \
      --query 'RouteTables[0].Associations[?!Main].RouteTableAssociationId' --output text); do
    a disassociate-route-table --association-id "$assoc"
  done
  a delete-route-table --route-table-id "$rt"
done
a delete-nat-gateway --nat-gateway-id "$(id '["nat"]')"
aws --endpoint-url "$ENDPOINT" ec2 wait nat-gateway-deleted --nat-gateway-ids "$(id '["nat"]')"
a release-address --allocation-id "$(id '["eip"]')"
a detach-internet-gateway --internet-gateway-id "$(id '["igw"]')" --vpc-id "$(id '["vpc"]')"
a delete-internet-gateway --internet-gateway-id "$(id '["igw"]')"
for s in $(id '["public_subnets"]') $(id '["private_subnets"]'); do a delete-subnet --subnet-id "$s"; done
a delete-vpc --vpc-id "$(id '["vpc"]')"
LEFT=$(aws --endpoint-url "$ENDPOINT" ec2 describe-vpcs --filters Name=tag:lab,Values=06 --query 'length(Vpcs)')
echo "$BACKEND reset-by-api: $(python3 -c "import time;print(round(time.time()-$T0,1))")s, lab VPCs left: $LEFT"
