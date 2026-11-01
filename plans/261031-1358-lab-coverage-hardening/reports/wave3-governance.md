# Wave 3 — governance (group E) registry report

Status: DONE_WITH_CONCERNS. All 17 kinds load and draw. The 10 builder kinds each pass their contract on live Floci 2.3.0, run through `prepare` and the aws CLI with the real `shapes.py`. A live collect of every kind gives no warnings, and coverage shows no gap left (121 gaps before, 0 after, across all wave-3 groups). The concerns are listed under "Needs outside my files".

## Files (all new)

| File | Lines |
|---|---|
| `server/src/cloudy_labs/registry/cloudtrail.yaml` | 72 |
| `server/src/cloudy_labs/registry/config.yaml` | 139 |
| `server/src/cloudy_labs/registry/cognito-idp.yaml` | 116 |
| `server/src/cloudy_labs/registry/cognito-identity.yaml` | 65 |
| `server/src/cloudy_labs/registry/budgets.yaml` | 59 |
| `server/src/cloudy_labs/registry/organizations.yaml` | 72 |
| `server/src/cloudy_labs/registry/guardduty.yaml` | 22 |
| `server/src/cloudy_labs/registry/inspector2.yaml` | 22 |
| `server/src/cloudy_labs/registry/securityhub.yaml` | 23 |
| `server/src/cloudy_labs/registry/network-firewall.yaml` | 191 |
| `server/src/cloudy_labs/registry/controltower.yaml` | 23 |
| `server/tests/test_registry_governance.py` | 167 (92 tests, all pass) |

## Kinds and view orders

| Order | Kind | Service | Scope / parent | Builder (create / modify / delete) | Icon |
|---|---|---|---|---|---|
| 700 | cloudtrail-trail | cloudtrail | region | create-trail / start-logging / delete-trail | Arch_AWS-CloudTrail_48.svg |
| 702 | config-recorder | config | region | put-configuration-recorder / put-delivery-channel (connect to bucket), start-configuration-recorder / delete-configuration-recorder | Arch_AWS-Config_48.svg (curve_segments 3: 1706 triangles; the default would be 2098) |
| 703 | config-rule | config | region | put-config-rule / start-config-rules-evaluation / delete-config-rule | Res_Documents_48_Light.svg |
| 705 | cognito-user-pool | cognito-idp | region | create-user-pool / update-user-pool / delete-user-pool | Arch_Amazon-Cognito_48.svg |
| 706 | cognito-identity-provider | cognito-idp | region (listed per user pool) | create / update / delete-identity-provider | Res_Authenticated-User_48_Light.svg |
| 707 | cognito-identity-pool | cognito-identity | region | create-identity-pool / set-identity-pool-roles / delete-identity-pool | Res_Users_48_Light.svg |
| 710 | budget | budgets | global | create-budget / update-budget / delete-budget | Arch_AWS-Budgets_48.svg |
| 712 | organization | organizations | global | list-only | Arch_AWS-Organizations_48.svg |
| 713 | organizational-unit | organizations | global | list-only | Res_AWS-Organizations_Organizational-Unit_48.svg |
| 714 | org-account | organizations | global | list-only | Res_AWS-Organizations_Account_48.svg |
| 716 | guardduty-detector | guardduty | region | list-only | Arch_Amazon-GuardDuty_48.svg |
| 718 | inspector | inspector2 | region | list-only | Arch_Amazon-Inspector_48.svg |
| 720 | securityhub-hub | securityhub | region | list-only | Arch_AWS-Security-Hub_48.svg |
| 722 | network-firewall | network-firewall | vpc (or region) | create-firewall / associate-firewall-policy (connect) / delete-firewall | Res_AWS-Network-Firewall_Endpoints_48.svg |
| 723 | firewall-policy | network-firewall | region | create / update / delete-firewall-policy | Arch_AWS-Network-Firewall_48.svg |
| 724 | firewall-rule-group | network-firewall | region | create / update / delete-firewall-rule-group | Res_Firewall_48_Light.svg |
| 726 | landing-zone | controltower | region | list-only | Arch_AWS-Control-Tower_48.svg |

Edges (all on my kinds, none on an existing kind):
- From the trail: delivers-to s3-bucket, delivers-to log-group, execution-role iam-role, and encrypted-by kms-key/kms-alias.
- From the config recorder: execution-role and delivers-to bucket. A config rule invokes lambda-function for CUSTOM_LAMBDA rules.
- From the user pool: invokes lambda (its triggers).
- provider-of (identity provider to user pool); federates (identity pool to user pool); pool-role (identity pool to iam-role).
- uses-firewall-policy, firewall-subnet, and uses-rule-group.
- member-of (OU to organization; account to OU and organization).

The network-firewall rule-group op ids are named `*-firewall-rule-group`, so they do not collide with the WAF `rule group` ops. Both kinds own the coverage noun "rule group" through their own `RuleGroup` action.

## Verification

- **Contracts:** all 10 builder kinds pass on live Floci through `prepare` and the aws CLI, polling a live collect for each expectation. That includes the config contracts against the coordinator's `config` to `configservice` fix in `shapes.py`.
- **Update ops checked by hand:**
  - update-firewall-rule-group and update-firewall-policy work with a live `UpdateToken`, and a stale token gets `InvalidTokenException`.
  - update-identity-provider and update-user-pool run inside their contracts.
- **Live collect:** one of every kind gives no warnings, and every node and edge listed above was drawn, with these exceptions:
  - The trail's log-group, role and key edges, because Floci drops those fields (caveat).
  - securityhub-hub, which was not enabled on shared Floci because Floci has no DisableSecurityHub.
- **Tests:**
  - `uv run pytest -q tests/test_registry_governance.py`: 92 passed.
  - Full suite: 860 passed and 8 failed. Two of the failures are the expected golden/matrix ones. The other six are replay failures; see the first item under "Needs outside my files".
- **No secrets read:**
  - The identity provider picks only `AttributeMapping` and `IdpIdentifiers`, never `ProviderDetails` (where the client secret lives).
  - Org accounts never read `Email`.
  - The user pool reads only the minimum length of its password policy, as `minimumLength`.
  - `updateToken` on the policy and rule group is an optimistic-lock value that `Update*` must echo. It is not a credential, and it is what the modify ops need.

## make_governance(c)

This was tested once on live Floci with `prefix="pb-governance-", sticky=False`. It ran without error, and the collect showed every kind except securityhub-hub (skipped by `sticky=False`), with no warnings. All of it was then deleted. Call it as `make_governance(c)` on the fresh recording Floci: that uses `w3-` names and also enables Inspector and Security Hub, which cannot be undone on Floci.

```python
import json


def make_governance(c, prefix="w3-", sticky=True):
    """One of every governance kind, linked as AWS links them. c: service name -> boto3 client on Floci.

    sticky=False skips Inspector and Security Hub, which Floci 2.3.0 cannot disable once enabled."""
    region = c("sts").meta.region_name
    under = prefix.replace("-", "_")
    s3, iam = c("s3"), c("iam")
    bucket = f"{prefix}governance-logs"
    s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})
    trust = lambda principal: json.dumps({"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": principal, "Action": "sts:AssumeRole" if "Service" in principal else "sts:AssumeRoleWithWebIdentity"}]})
    config_role = iam.create_role(RoleName=f"{prefix}config", AssumeRolePolicyDocument=trust({"Service": "config.amazonaws.com"}))["Role"]["Arn"]
    auth_role = iam.create_role(RoleName=f"{prefix}cognito-auth", AssumeRolePolicyDocument=trust({"Federated": "cognito-identity.amazonaws.com"}))["Role"]["Arn"]

    # CloudTrail: a trail to the bucket, logging. Floci 2.3.0 drops a trail's log group, role and KMS key.
    ct = c("cloudtrail")
    ct.create_trail(Name=f"{prefix}trail", S3BucketName=bucket)
    ct.start_logging(Name=f"{prefix}trail")

    # Config: a recorder with its role and delivery channel, recording, and a managed rule.
    cfg = c("config")
    cfg.put_configuration_recorder(ConfigurationRecorder={"name": f"{prefix}recorder", "roleARN": config_role,
                                                          "recordingGroup": {"allSupported": True}})
    cfg.put_delivery_channel(DeliveryChannel={"name": f"{prefix}channel", "s3BucketName": bucket})
    cfg.start_configuration_recorder(ConfigurationRecorderName=f"{prefix}recorder")
    cfg.put_config_rule(ConfigRule={"ConfigRuleName": f"{prefix}bucket-versioning",
                                    "Source": {"Owner": "AWS", "SourceIdentifier": "S3_BUCKET_VERSIONING_ENABLED"},
                                    "Scope": {"ComplianceResourceTypes": ["AWS::S3::Bucket"]}})

    # Cognito: a user pool with an OIDC provider (no client secret), and an identity pool federating it.
    idp = c("cognito-idp")
    pool = idp.create_user_pool(PoolName=f"{prefix}users", Policies={"PasswordPolicy": {"MinimumLength": 10}})["UserPool"]["Id"]
    idp.create_identity_provider(UserPoolId=pool, ProviderName=f"{prefix}oidc", ProviderType="OIDC",
                                 ProviderDetails={"client_id": "dummy-client", "authorize_scopes": "openid email",
                                                  "attributes_request_method": "GET", "oidc_issuer": "https://issuer.example.com"},
                                 AttributeMapping={"email": "email"})
    ci = c("cognito-identity")
    ipool = ci.create_identity_pool(IdentityPoolName=f"{under}identities", AllowUnauthenticatedIdentities=False,
                                    CognitoIdentityProviders=[{"ProviderName": f"cognito-idp.{region}.amazonaws.com/{pool}",
                                                               "ClientId": "dummy-client"}])["IdentityPoolId"]
    ci.set_identity_pool_roles(IdentityPoolId=ipool, Roles={"authenticated": auth_role})

    # Budgets (global): a monthly cost budget.
    account = c("sts").get_caller_identity()["Account"]
    c("budgets").create_budget(AccountId=account, Budget={"BudgetName": f"{prefix}monthly", "BudgetType": "COST", "TimeUnit": "MONTHLY",
                                                          "BudgetLimit": {"Amount": "50", "Unit": "USD"}})

    # Network Firewall: a rule group in a policy, used by a firewall in a VPC subnet.
    ec2 = c("ec2")
    vpc = ec2.create_vpc(CidrBlock="10.71.0.0/16", TagSpecifications=[{"ResourceType": "vpc", "Tags": [{"Key": "Name", "Value": f"{prefix}inspection"}]}])["Vpc"]["VpcId"]
    subnet = ec2.create_subnet(VpcId=vpc, CidrBlock="10.71.1.0/28", AvailabilityZone=f"{region}a",
                               TagSpecifications=[{"ResourceType": "subnet", "Tags": [{"Key": "Name", "Value": f"{prefix}firewall"}]}])["Subnet"]["SubnetId"]
    nf = c("network-firewall")
    rules = nf.create_rule_group(RuleGroupName=f"{prefix}allow-web", Type="STATEFUL", Capacity=100, RuleGroup={
        "RulesSource": {"RulesString": 'pass tcp any any -> any 443 (msg:"allow https"; sid:1; rev:1;)'}})["RuleGroupResponse"]["RuleGroupArn"]
    policy = nf.create_firewall_policy(FirewallPolicyName=f"{prefix}policy", FirewallPolicy={
        "StatelessDefaultActions": ["aws:forward_to_sfe"], "StatelessFragmentDefaultActions": ["aws:forward_to_sfe"],
        "StatefulRuleGroupReferences": [{"ResourceArn": rules}]})["FirewallPolicyResponse"]["FirewallPolicyArn"]
    nf.create_firewall(FirewallName=f"{prefix}firewall", FirewallPolicyArn=policy, VpcId=vpc, SubnetMappings=[{"SubnetId": subnet}],
                       DeleteProtection=False, SubnetChangeProtection=False, FirewallPolicyChangeProtection=False)

    # Organizations (global): an organization with an OU holding one created account.
    org = c("organizations")
    org.create_organization(FeatureSet="ALL")
    root = org.list_roots()["Roots"][0]["Id"]
    ou = org.create_organizational_unit(ParentId=root, Name=f"{prefix}workloads")["OrganizationalUnit"]["Id"]
    status = org.create_account(Email=f"{prefix}member@example.invalid", AccountName=f"{prefix}member")["CreateAccountStatus"]
    member = status.get("AccountId") or org.describe_create_account_status(CreateAccountRequestId=status["Id"])["CreateAccountStatus"]["AccountId"]
    org.move_account(AccountId=member, SourceParentId=root, DestinationParentId=ou)

    # GuardDuty, Inspector, Security Hub and Control Tower: account-level switches.
    c("guardduty").create_detector(Enable=True, FindingPublishingFrequency="FIFTEEN_MINUTES")
    c("controltower").create_landing_zone(version="3.3", manifest={"governedRegions": [region]})
    if sticky:
        c("inspector2").enable(resourceTypes=["EC2", "ECR"])
        c("securityhub").enable_security_hub(EnableDefaultStandards=False)
```

The `sticky=True` path (`enable_security_hub`) is the one line never run live. `EnableSecurityHub` is in the Floci 2.3.0 supported list, and the hub kind reads it through `DescribeHub`.

## Floci 2.3.0 quirks (all checked live, all recorded as caveats)

- **CloudTrail:**
  - A log file reaches the bucket about once a minute, but it holds only S3 data events. There are no management events, and LookupEvents answers nothing.
  - A missing bucket or a missing bucket policy is accepted.
  - **CreateTrail and UpdateTrail drop CloudWatchLogsLogGroupArn, CloudWatchLogsRoleArn and KmsKeyId** (`cloudtrail-logs-and-key-dropped`).
- **Config:**
  - The recorder starts with no delivery channel.
  - It delivers no snapshot.
  - Rules never evaluate and stay at INSUFFICIENT_DATA.
  - Rule tags are ignored.
  - Config is control-plane-only.
- **Cognito:**
  - IdentityPoolName accepts a dash.
  - An identity pool accepts a user-pool provider whose pool does not exist (checked live with `ap-southeast-2_doesnotexist`).
  - Identity provider details are not checked.
- **Budgets:** there is no spend (actualSpend stays 0). The service is control-plane-only.
- **Organizations:** CreateAccount succeeds at once, with no real account behind it.
- **GuardDuty:** ListFindings is an unknown operation, so there are no findings.
- **Inspector:** Floci has no ListFindings, ListCoverage or Disable, so scanning once enabled stays on.
- **Security Hub:** Floci has no GetFindings, standards APIs or DisableSecurityHub.
- **Network Firewall:**
  - Nothing is filtered.
  - Missing policy or subnet references are accepted, and policies or rule groups still in use can be deleted.
  - CreateFirewall turns all three protections on when they are omitted. The builder sends false for each.
  - **The `Rules` string of CreateRuleGroup and UpdateRuleGroup is dropped** (`network-firewall-rules-flag-dropped`). The create default now puts the Suricata rules inside `RuleGroup.RulesSource.RulesString`, which Floci keeps.
- **Control Tower:** CreateLandingZone is ACTIVE at once and creates nothing behind it: no org, OU, trail or Config rule (checked live).

## Missing Floci APIs (why kinds are list-only or limited)

- inspector2: Disable, ListFindings, ListCoverage.
- securityhub: DisableSecurityHub, GetFindings, BatchImportFindings, GetEnabledStandards.
- guardduty: ListFindings and GetFindings.
- network-firewall: TagResource and UntagResource. Tags are given at create.

## Needs outside my files

1. **The replay fixtures (`tests/graph_fixtures.py`, `test_collector_replay*.py`).**
   - **Wave 2:** `wave_2_graph()` collects every registry kind, so each wave-3 service is unrecorded and gives a "no fake client for <service>" warning. This covers all wave-3 groups, mine included (budgets, cloudtrail, cognito-identity, cognito-idp, config, controltower, guardduty, inspector2, network-firewall, organizations, securityhub). The fix is to pin the replay to the kinds that recording covers, or to add the wave-3 recording.
   - **Wave 1:** this fails on `rds.describe_event_subscriptions`, which belongs to the datamove group, not to me.
2. **`builder/shapes.py` `CLI_SERVICE`.** `"config": "configservice"` was needed; the coordinator has applied it. All Config ops and contracts now pass against the real file.
3. **Organizations: nested OUs are not drawn.** Only OUs directly under the root are listed, because a scoped list cannot recurse. Accounts in a nested OU still show, but their member-of edge to that OU is not drawn. Drawing deeper OUs needs a recursion hook or a recursive scoped list in the collector.
4. **Shared Floci state I could not undo.**
   - Inspector2 was enabled for EC2 and ECR on shared Floci during exploration. Floci has no Disable, so an `inspector` node now shows on shared Floci.
   - One KMS key (description `pb-governance-trail`) is in PendingDeletion with a 7-day window, which is the shortest KMS allows.
   - Every other pb-governance resource is deleted, including the organization (none exists now) and the landing zones.

## Coverage before and after

From `uv run labctl coverage --catalog ../plans/reports/researcher-261031-1358-labaws-catalog-and-floci-coverage.csv --json`:

| | blocked | gap | ready-with-caveats | ready |
|---|---|---|---|---|
| Before (all groups) | 61 | 121 | 347 | 1 |
| After (all groups) | 61 | 0 | 468 | 1 |

My services (gap before → ready-with-caveats after):

| Service | Labs moved from gap to ready-with-caveats |
|---|---|
| cloudtrail | 9 |
| config | 4 |
| cognito-idp | 4 |
| network-firewall | 4 |
| budgets | 3 |
| organizations | 2 |
| guardduty | 1 |
| controltower | 1 |

None of the after-run reasons or warnings names a governance service or noun ("rule group", "user pool", "identity provider", and the rest).

```text
Status: DONE_WITH_CONCERNS
Summary: 17 governance kinds across 11 YAML files and a 92-test file; all 10 builder contracts pass on live Floci, a live collect of every kind gives no warnings, and coverage gaps for these services are gone.
Concerns/Blockers: replay fixtures must be pinned or re-recorded for wave-3 services; nested OUs are not drawn; Inspector stays enabled on shared Floci and one KMS key is pending deletion.
```
