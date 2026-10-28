#!/usr/bin/env bash
# Runs the same read and write calls directly and through api-tap, then diffs the outputs.
# Usage: ./api-tap-compare.sh <direct-endpoint> <tap-endpoint>   (api-tap must already be running)
set -uo pipefail
DIRECT=${1:-http://localhost:4566}; TAP=${2:-http://localhost:4580}
OUT="$(dirname "$0")/out/api-tap"; rm -rf "$OUT"; mkdir -p "$OUT/direct" "$OUT/tap"
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
VPC=$(python3 -c "import json;print(json.load(open('$(dirname "$0")/out/floci/ids.json'))['vpc'])")
F="Name=vpc-id,Values=$VPC"
reads=(
  "describe-vpcs|ec2 describe-vpcs --vpc-ids $VPC"
  "describe-availability-zones|ec2 describe-availability-zones"
  "describe-subnets|ec2 describe-subnets --filters $F"
  "describe-internet-gateways|ec2 describe-internet-gateways --filters Name=attachment.vpc-id,Values=$VPC"
  "describe-nat-gateways|ec2 describe-nat-gateways --filter $F"
  "describe-route-tables|ec2 describe-route-tables --filters $F"
  "describe-security-groups|ec2 describe-security-groups --filters $F"
  "describe-key-pairs|ec2 describe-key-pairs"
  "describe-instances|ec2 describe-instances --filters $F"
  "sts-get-caller-identity|sts get-caller-identity"
)
for mode in direct tap; do
  ep=$DIRECT; [ $mode = tap ] && ep=$TAP
  for r in "${reads[@]}"; do
    name=${r%%|*}; cmd=${r#*|}
    # shellcheck disable=SC2086
    aws --endpoint-url "$ep" --output json $cmd >"$OUT/$mode/$name.json" 2>"$OUT/$mode/$name.err"; echo $? >"$OUT/$mode/$name.rc"
  done
done
echo "== read diff (direct vs tap)"
diff -r "$OUT/direct" "$OUT/tap" && echo "identical: ${#reads[@]} read calls"

echo "== writes through tap"
w() { aws --endpoint-url "$TAP" "$@" >/dev/null 2>>"$OUT/tap-writes.err" && echo "ok   $*" || echo "FAIL $*"; }
SG=$(aws --endpoint-url "$TAP" ec2 create-security-group --vpc-id "$VPC" --group-name tap-probe --description probe --query GroupId --output text)
echo "ok   ec2 create-security-group -> $SG"
w ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 443 --cidr 0.0.0.0/0
w ec2 create-tags --resources "$SG" --tags Key=via,Value=api-tap
w ec2 delete-security-group --group-id "$SG"
w s3api create-bucket --bucket tap-probe
printf 'hello through the tap\n' >"$OUT/probe.txt"
w s3 cp "$OUT/probe.txt" s3://tap-probe/probe.txt
aws --endpoint-url "$TAP" s3 cp s3://tap-probe/probe.txt - 2>>"$OUT/tap-writes.err" | cmp - "$OUT/probe.txt" && echo "ok   s3 round-trip content identical"
w s3 rm s3://tap-probe/probe.txt
w s3api delete-bucket --bucket tap-probe
