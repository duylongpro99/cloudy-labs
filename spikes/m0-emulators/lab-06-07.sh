#!/usr/bin/env bash
# Runs the Lab 6 + 7 command sequence against one emulator and records every step.
# Usage: ./lab-06-07.sh <backend-name> <endpoint-url> [out-root]
# Each step writes out/<backend>/<NN-step>.json (stdout), .err (stderr) and .rc (exit code).
set -uo pipefail

BACKEND=${1:?backend name, e.g. floci}
ENDPOINT=${2:?endpoint url, e.g. http://localhost:4566}
OUT_ROOT=${3:-"$(dirname "$0")/out"}
OUT="$OUT_ROOT/$BACKEND"
rm -rf "$OUT" && mkdir -p "$OUT"

export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
REGION=us-east-1

# run <name> <aws args...>: records output, prints a one-line status, echoes stdout for capture.
run() {
  local name=$1; shift
  # Count files, not a variable: run() is often called inside $(...) subshells.
  local STEP; STEP=$(( $(find "$OUT" -name '*.rc' | wc -l) + 1 ))
  local base; base=$(printf '%s/%02d-%s' "$OUT" "$STEP" "$name")
  local t0 t1
  t0=$(python3 -c 'import time;print(time.time())')
  aws --endpoint-url "$ENDPOINT" --output json "$@" >"$base.json" 2>"$base.err"
  local rc=$?
  t1=$(python3 -c 'import time;print(time.time())')
  echo "$rc" >"$base.rc"
  printf '%-6s %02d %-34s rc=%s %4.0fms\n' "$BACKEND" "$STEP" "$name" "$rc" "$(python3 -c "print(($t1-$t0)*1000)")" >&2
  cat "$base.json"
}

# jq-free field extraction from the last JSON on stdin.
pick() { python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print(''); sys.exit()
for k in sys.argv[1].split('.'):
    d = d[int(k)] if isinstance(d, list) else (d or {}).get(k)
print(d if d is not None else '')" "$1"; }

tags() { echo "ResourceType=$1,Tags=[{Key=Name,Value=$2},{Key=lab,Value=06}]"; }

# --- Lab 6: VPC from scratch ---
VPC=$(run create-vpc ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications "$(tags vpc lab06-vpc)" | pick Vpc.VpcId)
run enable-dns-hostnames ec2 modify-vpc-attribute --vpc-id "$VPC" --enable-dns-hostnames '{"Value":true}' >/dev/null

PUB_A=$(run create-subnet-public-a ec2 create-subnet --vpc-id "$VPC" --cidr-block 10.0.1.0/24 --availability-zone ${REGION}a --tag-specifications "$(tags subnet lab06-public-a)" | pick Subnet.SubnetId)
PUB_B=$(run create-subnet-public-b ec2 create-subnet --vpc-id "$VPC" --cidr-block 10.0.2.0/24 --availability-zone ${REGION}b --tag-specifications "$(tags subnet lab06-public-b)" | pick Subnet.SubnetId)
PRI_A=$(run create-subnet-private-a ec2 create-subnet --vpc-id "$VPC" --cidr-block 10.0.11.0/24 --availability-zone ${REGION}a --tag-specifications "$(tags subnet lab06-private-a)" | pick Subnet.SubnetId)
PRI_B=$(run create-subnet-private-b ec2 create-subnet --vpc-id "$VPC" --cidr-block 10.0.12.0/24 --availability-zone ${REGION}b --tag-specifications "$(tags subnet lab06-private-b)" | pick Subnet.SubnetId)
run map-public-ip-a ec2 modify-subnet-attribute --subnet-id "$PUB_A" --map-public-ip-on-launch >/dev/null
run map-public-ip-b ec2 modify-subnet-attribute --subnet-id "$PUB_B" --map-public-ip-on-launch >/dev/null

IGW=$(run create-igw ec2 create-internet-gateway --tag-specifications "$(tags internet-gateway lab06-igw)" | pick InternetGateway.InternetGatewayId)
run attach-igw ec2 attach-internet-gateway --internet-gateway-id "$IGW" --vpc-id "$VPC" >/dev/null

EIP=$(run allocate-eip ec2 allocate-address --domain vpc | pick AllocationId)
NAT=$(run create-nat ec2 create-nat-gateway --subnet-id "$PUB_A" --allocation-id "$EIP" --tag-specifications "$(tags natgateway lab06-nat)" | pick NatGateway.NatGatewayId)
run wait-nat-available ec2 wait nat-gateway-available --nat-gateway-ids "$NAT" >/dev/null

RT_PUB=$(run create-rt-public ec2 create-route-table --vpc-id "$VPC" --tag-specifications "$(tags route-table lab06-rt-public)" | pick RouteTable.RouteTableId)
RT_PRI=$(run create-rt-private ec2 create-route-table --vpc-id "$VPC" --tag-specifications "$(tags route-table lab06-rt-private)" | pick RouteTable.RouteTableId)
run route-public-igw ec2 create-route --route-table-id "$RT_PUB" --destination-cidr-block 0.0.0.0/0 --gateway-id "$IGW" >/dev/null
run route-private-nat ec2 create-route --route-table-id "$RT_PRI" --destination-cidr-block 0.0.0.0/0 --nat-gateway-id "$NAT" >/dev/null
run assoc-public-a ec2 associate-route-table --route-table-id "$RT_PUB" --subnet-id "$PUB_A" >/dev/null
run assoc-public-b ec2 associate-route-table --route-table-id "$RT_PUB" --subnet-id "$PUB_B" >/dev/null
run assoc-private-a ec2 associate-route-table --route-table-id "$RT_PRI" --subnet-id "$PRI_A" >/dev/null
run assoc-private-b ec2 associate-route-table --route-table-id "$RT_PRI" --subnet-id "$PRI_B" >/dev/null

# --- Lab 7: security group, key pair, instance with UserData ---
SG=$(run create-sg ec2 create-security-group --vpc-id "$VPC" --group-name lab07-web --description "Lab 7 web" | pick GroupId)
run sg-ingress-22 ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 22 --cidr 203.0.113.10/32 >/dev/null
run sg-ingress-80 ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null
run create-key-pair ec2 create-key-pair --key-name lab07-key --query '{KeyName:KeyName,KeyPairId:KeyPairId,KeyFingerprint:KeyFingerprint}' >/dev/null

USER_DATA=$(cat <<'UD'
#!/bin/sh
mkdir -p /srv/www
echo "<h1>XLabs Lab 7 web server</h1>" > /srv/www/index.html
# Floci binds an IMDS proxy on 169.254.169.254:80 inside the instance, so 0.0.0.0:80 is taken;
# bind to the instance's own private address instead.
IP=$(python3 -c "import urllib.request as u;print(u.urlopen('http://169.254.169.254/latest/meta-data/local-ipv4').read().decode())" 2>/dev/null)
cd /srv/www && nohup python3 -m http.server 80 ${IP:+--bind $IP} >/var/log/web.log 2>&1 &
UD
)
INSTANCE=$(run run-instances ec2 run-instances --image-id ami-amazonlinux2023-arm64 --instance-type t4g.micro \
  --subnet-id "$PUB_A" --security-group-ids "$SG" --key-name lab07-key --user-data "$USER_DATA" \
  --tag-specifications "$(tags instance lab07-web)" | pick Instances.0.InstanceId)
run wait-instance-running ec2 wait instance-running --instance-ids "$INSTANCE" >/dev/null

# --- describe-* evidence for the resource graph (filtered to the lab VPC where the API allows) ---
F="Name=vpc-id,Values=$VPC"
run describe-vpcs ec2 describe-vpcs --vpc-ids "$VPC" >/dev/null
run describe-availability-zones ec2 describe-availability-zones >/dev/null
run describe-subnets ec2 describe-subnets --filters "$F" >/dev/null
run describe-internet-gateways ec2 describe-internet-gateways --filters "Name=attachment.vpc-id,Values=$VPC" >/dev/null
run describe-nat-gateways ec2 describe-nat-gateways --filter "$F" >/dev/null
run describe-route-tables ec2 describe-route-tables --filters "$F" >/dev/null
run describe-security-groups ec2 describe-security-groups --filters "$F" >/dev/null
run describe-key-pairs ec2 describe-key-pairs >/dev/null
run describe-instances ec2 describe-instances --filters "$F" >/dev/null

cat >"$OUT/ids.json" <<JSON
{"vpc":"$VPC","public_subnets":["$PUB_A","$PUB_B"],"private_subnets":["$PRI_A","$PRI_B"],
 "igw":"$IGW","eip":"$EIP","nat":"$NAT","rt_public":"$RT_PUB","rt_private":"$RT_PRI",
 "sg":"$SG","instance":"$INSTANCE"}
JSON
echo "$BACKEND: $(find "$OUT" -name '*.rc' | wc -l | tr -d ' ') steps, $(grep -L '^0$' "$OUT"/*.rc | wc -l | tr -d ' ') failed" >&2
