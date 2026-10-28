#!/usr/bin/env bash
# Lab 3 against moto with IAM enforcement: does a least-privilege policy really deny?
# Usage: ./lab-03.sh [endpoint] [out-dir]
# moto_server must run with INITIAL_NO_AUTH_ACTION_COUNT=3: only the three calls that
# bootstrap an `admin` user are unauthenticated; everything after is signed by a real IAM key.
set -uo pipefail
EP=${1:-http://localhost:5050}
OUT=${2:-"$(dirname "$0")/out"}
rm -rf "$OUT" && mkdir -p "$OUT"
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
CFG="$OUT/.aws"; mkdir -p "$CFG"
export AWS_SHARED_CREDENTIALS_FILE="$CFG/credentials" AWS_CONFIG_FILE="$CFG/config"
: >"$AWS_SHARED_CREDENTIALS_FILE"

# run <name> <profile> <aws args...>: records stdout/stderr/rc, prints one status line.
run() {
  local name=$1 profile=$2; shift 2
  local base="$OUT/$name"
  AWS_PROFILE=$profile aws --endpoint-url "$EP" --output json "$@" >"$base.json" 2>"$base.err"
  local rc=$?; echo "$rc" >"$base.rc"
  local why; why=$(grep -o -E '\((AccessDenied|InvalidClientTokenId|SignatureDoesNotMatch|[A-Za-z]+)\)' "$base.err" | head -1)
  printf '%-40s %-6s rc=%s %s\n' "$name" "$profile" "$rc" "$why" | tee -a "$OUT/summary.txt" >&2
  cat "$base.json"
}
save_key() { # save_key <profile> <create-access-key json on stdin>
  python3 -c "import json,sys;k=json.load(sys.stdin)['AccessKey'];print(f\"[$1]\naws_access_key_id = {k['AccessKeyId']}\naws_secret_access_key = {k['SecretAccessKey']}\n\")" >>"$AWS_SHARED_CREDENTIALS_FILE"
}
printf '[bootstrap]\naws_access_key_id = AKIAIOSFODNN7EXAMPLE\naws_secret_access_key = bootstrap\n\n' >>"$AWS_SHARED_CREDENTIALS_FILE"
policy() { python3 -c "import json,sys;print(json.dumps({'Version':'2012-10-17','Statement':json.loads(sys.argv[1])}))" "$1"; }

# --- bootstrap (the only unauthenticated calls) ---
run 00-create-user-admin bootstrap iam create-user --user-name admin >/dev/null
run 01-put-admin-policy bootstrap iam put-user-policy --user-name admin --policy-name all \
  --policy-document "$(policy '[{"Effect":"Allow","Action":"*","Resource":"*"}]')" >/dev/null
run 02-create-key-admin bootstrap iam create-access-key --user-name admin | save_key admin
run 03-bootstrap-key-now-rejected bootstrap iam list-users >/dev/null

# --- Lab 3 setup as admin ---
run 10-create-bucket admin s3api create-bucket --bucket lab03 >/dev/null
run 11-create-user-alice admin iam create-user --user-name alice >/dev/null
P_BASE=$(run 12-create-policy-baseline admin iam create-policy --policy-name lab03-alice-prefix \
  --policy-document "$(policy '[{"Effect":"Allow","Action":"s3:PutObject","Resource":"arn:aws:s3:::lab03/alice/*"}]')" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["Policy"]["Arn"])')
run 13-attach-baseline admin iam attach-user-policy --user-name alice --policy-arn "$P_BASE" >/dev/null
run 14-create-key-alice admin iam create-access-key --user-name alice | save_key alice
echo hello >"$OUT/x.txt"

# --- case 1: baseline Allow on alice/* ---
run 20-baseline-put-alice alice s3api put-object --bucket lab03 --key alice/x --body "$OUT/x.txt" >/dev/null
run 21-baseline-put-bob alice s3api put-object --bucket lab03 --key bob/x --body "$OUT/x.txt" >/dev/null
run 22-baseline-list-users alice iam list-users >/dev/null
run 23-baseline-get-alice alice s3api get-object --bucket lab03 --key alice/x "$OUT/get.txt" >/dev/null

# --- case 2: broad Allow lab03/* plus explicit Deny on bob/* ---
run 30-detach-baseline admin iam detach-user-policy --user-name alice --policy-arn "$P_BASE" >/dev/null
P_DENY=$(run 31-create-policy-deny admin iam create-policy --policy-name lab03-explicit-deny \
  --policy-document "$(policy '[{"Effect":"Allow","Action":"s3:PutObject","Resource":"arn:aws:s3:::lab03/*"},{"Effect":"Deny","Action":"s3:PutObject","Resource":"arn:aws:s3:::lab03/bob/*"}]')" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["Policy"]["Arn"])')
run 32-attach-deny admin iam attach-user-policy --user-name alice --policy-arn "$P_DENY" >/dev/null
run 33-deny-put-alice alice s3api put-object --bucket lab03 --key alice/y --body "$OUT/x.txt" >/dev/null
run 34-deny-put-bob alice s3api put-object --bucket lab03 --key bob/y --body "$OUT/x.txt" >/dev/null
run 35-deny-put-other alice s3api put-object --bucket lab03 --key carol/y --body "$OUT/x.txt" >/dev/null

# --- case 3: Allow with a Condition on server-side encryption ---
run 40-detach-deny admin iam detach-user-policy --user-name alice --policy-arn "$P_DENY" >/dev/null
P_COND=$(run 41-create-policy-condition admin iam create-policy --policy-name lab03-require-sse \
  --policy-document "$(policy '[{"Effect":"Allow","Action":"s3:PutObject","Resource":"arn:aws:s3:::lab03/*","Condition":{"StringEquals":{"s3:x-amz-server-side-encryption":"AES256"}}}]')" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["Policy"]["Arn"])')
run 42-attach-condition admin iam attach-user-policy --user-name alice --policy-arn "$P_COND" >/dev/null
run 43-condition-put-with-sse alice s3api put-object --bucket lab03 --key alice/z --body "$OUT/x.txt" --server-side-encryption AES256 >/dev/null
run 44-condition-put-without-sse alice s3api put-object --bucket lab03 --key alice/z2 --body "$OUT/x.txt" >/dev/null

# --- case 4: simulate-principal-policy (would let a checker ask "can alice do X?") ---
ALICE_ARN=$(AWS_PROFILE=admin aws --endpoint-url "$EP" iam get-user --user-name alice --query User.Arn --output text)
run 50-detach-condition admin iam detach-user-policy --user-name alice --policy-arn "$P_COND" >/dev/null
run 51-reattach-baseline admin iam attach-user-policy --user-name alice --policy-arn "$P_BASE" >/dev/null
run 52-simulate-principal-policy admin iam simulate-principal-policy --policy-source-arn "$ALICE_ARN" \
  --action-names s3:PutObject --resource-arns arn:aws:s3:::lab03/alice/x arn:aws:s3:::lab03/bob/x >/dev/null
run 53-simulate-custom-policy admin iam simulate-custom-policy --action-names s3:PutObject \
  --resource-arns arn:aws:s3:::lab03/bob/x \
  --policy-input-list "$(policy '[{"Effect":"Allow","Action":"s3:PutObject","Resource":"arn:aws:s3:::lab03/alice/*"}]')" >/dev/null
