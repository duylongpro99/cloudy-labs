# Wave 2: data and config kinds (CloudFormation, DynamoDB, KMS, SSM, Secrets Manager)

## Outcome

Six kinds were added in five registry files. They all load, every op resolves against botocore,
and every contract step builds a request botocore accepts. A live collect over Floci (1.7 s, no
warnings) found every probe resource with the right parent, props and edges, including the
managed-by edges from CloudFormation-made resources to their stack. No value is read anywhere:
there are no GetParameter(s), GetSecretValue or GetTemplate calls, and no Outputs or Parameters.

The SSM document kind was **not** added: Floci 2.3.0 does not list CreateDocument, ListDocuments
or DescribeDocument as supported. A draft is included below for when it does.

Files:
- `server/src/cloudy_labs/registry/cloudformation.yaml` (new, 99 lines)
- `server/src/cloudy_labs/registry/dynamodb.yaml` (new, 109 lines)
- `server/src/cloudy_labs/registry/kms.yaml` (new, 118 lines)
- `server/src/cloudy_labs/registry/ssm.yaml` (new, 58 lines)
- `server/src/cloudy_labs/registry/secretsmanager.yaml` (new, 75 lines)
- `server/tests/test_registry_sensitive_props.py` (new, 31 lines). It checks that the chat_props and
  props of cloudformation-stack, ssm-parameter and secretsmanager-secret hold no deny-listed or
  value/outputs/parameters prop, read no Value/SecretString/Outputs/Parameters field, and call no
  value-reading API.

## Kinds added

| kind | parent | edges | ops | contract | view order |
|---|---|---|---|---|---|
| `kms-key` | region | none | create-kms-key, enable-key-rotation, disable-kms-key, enable-kms-key, schedule-key-deletion | create-kms-key, then enable-key-rotation and disable-kms-key | 110 |
| `kms-alias` | region | `alias-of` to kms-key, matched by KeyId (reference) | create-kms-alias, update-kms-alias (connect) | needs two keys; create-kms-alias, then update-kms-alias to the second key | 111 |
| `secretsmanager-secret` | region | `encrypted-by` to kms-key/kms-alias; `rotated-by` to lambda-function (both reference) | create-secret, rotate-secret (connect to lambda-function), cancel-rotate-secret, delete-secret | create-secret, then delete-secret | 112 |
| `dynamodb-table` | region | `encrypted-by` to kms-key/kms-alias; `reads-stream` from lambda-event-source (reverse, matched by EventSourceArn) | create-dynamodb-table, update-dynamodb-stream, add-dynamodb-gsi, update-time-to-live, update-continuous-backups, add-dynamodb-replica | create, then stream, TTL and PITR | 85 |
| `ssm-parameter` | region | `encrypted-by` to kms-key/kms-alias | put-ssm-parameter, label-parameter-version, delete-ssm-parameter | put, then label and delete | 120 |
| `cloudformation-stack` | region | `managed-by` from each created resource (reverse, see below); `execution-role` to iam-role | create-stack, update-stack, update-termination-protection, delete-stack | create (default one-parameter template), protection on/off, delete; max_seconds 5 | 130 |

Notes on the kinds:
- **GSIs** are the `globalIndexes` prop (name, keys, projection, status), and LSIs are `localIndexes`.
- **Streams** are props (`stream`, `streamArn`) plus the `reads-stream` edge.
- **Rotation** is props: `rotationEnabled`, `rotationLambda`, `rotationDays`, `rotationSchedule`,
  `lastRotated`, `nextRotation` and `pendingRotation`.
- **No prop name of the secret contains "secret".** CHAT_PROPS_DENY matches substrings.
- **Contract booleans are quoted strings** ("true"), because `coerce` calls `.lower()` on them.

The `managed-by` rules on the stack:
- The stack enriches with DescribeStackResources into `_Resources` (type, logical, physical, status).
- Per-type rules match the physical id by name:
  - S3 bucket on Name; DynamoDB table on TableName; KMS key on KeyId; KMS alias on AliasName.
  - IAM role, user, group and instance profile on their names.
  - Lambda function on FunctionName; event source mapping on UUID.
  - RDS DB instance, DB cluster and subnet group on their identifiers.
- One generic rule covers every kind whose node id is the physical id itself: the EC2/VPC kinds,
  iam-policy, ssm-parameter and secretsmanager-secret.
- Nothing is re-nested; the stack is a sibling under the region.
- Kinds from other wave-2 files (log-group, event-rule, backup-*) are not referenced, so this file
  does not depend on them. Their owners can add a rule each, for example
  `{kind: managed-by, target: "_Resources[?type=='AWS::Logs::LogGroup'].physical", match: logGroupName, to: log-group, reverse: true, style: reference}`.

Icons (paths under `aws-icon-pkg/`; nothing copied):
- `kms-key` and `kms-alias`: `Architecture-Service-Icons_07312026/Arch_Security-Identity/48/Arch_AWS-Key-Management-Service_48.svg`
- `secretsmanager-secret`: `Architecture-Service-Icons_07312026/Arch_Security-Identity/48/Arch_AWS-Secrets-Manager_48.svg`
- `dynamodb-table`: `Resource-Icons_07312026/Res_Databases/Res_Amazon-DynamoDB_Table_48.svg`
- `ssm-parameter`: `Resource-Icons_07312026/Res_Management-Governance/Res_AWS-Systems-Manager_Parameter-Store_48.svg`
- `cloudformation-stack`: `Resource-Icons_07312026/Res_Management-Governance/Res_AWS-CloudFormation_Stack_48.svg`

Op ids are prefixed (create-kms-alias and so on) because `create-alias` already belongs to lambda.

## APIs probed (all are in floci-ops-2.3.0.json and were called live)

- **kms:** ListKeys, DescribeKey, GetKeyRotationStatus, ListAliases, CreateKey, CreateAlias,
  UpdateAlias, DeleteAlias, EnableKeyRotation, DisableKey, EnableKey, ScheduleKeyDeletion.
- **dynamodb:** ListTables, DescribeTable, DescribeTimeToLive, DescribeContinuousBackups,
  DescribeGlobalTable, CreateTable, UpdateTable (stream, GSI, ReplicaUpdates), UpdateTimeToLive,
  UpdateContinuousBackups, CreateGlobalTable, ListGlobalTables, DeleteTable, TagResource.
  Also lambda CreateEventSourceMapping on a stream ARN.
- **ssm:** DescribeParameters, PutParameter (String, StringList, SecureString with a customer key),
  ListTagsForResource, AddTagsToResource, LabelParameterVersion, DeleteParameter, SendCommand,
  ListCommandInvocations, DescribeInstanceInformation.
- **secretsmanager:** ListSecrets (with and without IncludePlannedDeletion), DescribeSecret,
  CreateSecret, RotateSecret, CancelRotateSecret, ReplicateSecretToRegions,
  RemoveRegionsFromReplication, DeleteSecret (window and force), RestoreSecret.
  GetSecretValue was never called.
- **cloudformation:** CreateStack, UpdateStack, DescribeStacks, ListStacks, DescribeStackResources,
  UpdateTerminationProtection, DeleteStack.

## Floci quirks found

- **KMS**
  - Floci seeds 25 AWS-managed keys (KeyManager AWS) and their `alias/aws/*` aliases.
  - CreateAlias with a key ARN stores TargetKeyId as the bare key id.
  - The ScheduleKeyDeletion response has KeyState null. Afterwards DescribeKey says PendingDeletion
    but still has Enabled true.
  - GetKeyRotationStatus answers only KeyRotationEnabled.
- **DynamoDB**
  - SSEDescription.KMSMasterKeyArn is the key as given (often a bare key id).
  - Global tables are recorded but not real. CreateGlobalTable and UpdateTable ReplicaUpdates show up
    only in DescribeGlobalTable. DescribeTable never lists Replicas, no table exists in the replica
    region, and no item is copied.
  - A table that CloudFormation creates ignores `BillingMode: PAY_PER_REQUEST`: it has no
    BillingModeSummary and 5/5 provisioned capacity, so the scene says PROVISIONED. No caveat was
    added for this; the controller may want one on cloudformation-stack.
- **SSM**
  - DescribeParameters has no ARN, so the node id is the name. It is unique per region, and it is
    also the CloudFormation physical id.
  - CreateDocument, ListDocuments and DescribeDocument answer but are not in the supported list.
    They report SchemaVersion "1.0" when "2.2" was sent.
  - SendCommand accepts any instance id, even a made-up one. The command stays InProgress and the
    invocation stays Pending forever. DescribeInstanceInformation is empty because the EC2
    containers run no SSM agent.
- **Secrets Manager**
  - Rotation does not check its own result. An immediate rotation invokes the Lambda and sets
    LastRotatedDate even though the new version stays AWSPENDING (the function did nothing). A
    second RotateSecret then fails with "previous rotation isn't complete".
  - ReplicateSecretToRegions makes a real copy (InSync), and RemoveRegionsFromReplication deletes it.
  - A deleted secret leaves ListSecrets at once and is listed only with IncludePlannedDeletion.
- **CloudFormation**
  - Unknown resource types reach CREATE_COMPLETE with a placeholder physical id.
  - An invalid bucket name is accepted.
  - IAM resources are created without any capability, and Capabilities is reported empty.
  - Termination protection is enforced.
  - DeleteStack left two resources behind: the AWS::EC2::VPC of one stack and the AWS::KMS::Key of
    another (still Enabled). I deleted both by hand during cleanup.
  - DescribeStackResources on a deleted stack is a ValidationError (a ClientError), which enrich
    tolerates.

## Caveats added

- `kms-key`, prop `state`: `kms-enabled-while-pending`.
- `dynamodb-table`:
  - prop `replicas`: `control-plane-only` (global tables only recorded);
  - prop `kmsKey`: `dynamodb-kms-key-as-given`.
- `secretsmanager-secret`, prop `pendingRotation`: `secret-rotation-not-verified`.
- `cloudformation-stack`:
  - prop `status`: `cfn-no-validation` (unknown types and invalid properties still complete);
  - prop `capabilities`: `cfn-capabilities-not-required`.

**Not added: the Run Command caveat.** If it sat on ssm-parameter, parameter-only labs would be
flagged for no reason. I propose this on the `instance` kind, or as a catalog override for SSM
Run Command or Session Manager rows:
`{code: ssm-no-agent, text: "Floci 2.3.0 runs no SSM agent in its EC2 containers: SendCommand is accepted for any instance id but the command stays InProgress and its invocation Pending, and DescribeInstanceInformation lists no managed instance. Labs that need Run Command or Session Manager output cannot be checked."}`

**Possible addition:** a caveat on cloudformation-stack about resources left after DeleteStack
(VPC, KMS key). It was seen once per type, so I left it out rather than state it as a rule.

## Hook and schema needs (not done; files outside my ownership)

1. **Post-enrich filter (KMS).** `filter` runs before enrich, so AWS-managed keys can't be filtered
   by KeyManager. kms-key drops them with
   `id: "_Meta.KeyManager == 'CUSTOMER' && KeyArn || null"`.
   - It works, but each collect still pays DescribeKey and GetKeyRotationStatus for about 25 managed
     keys. The live collect of 10 kinds took 1.7 s in total.
   - Fix option 1: a filter that runs after enrich (`filter: {..., after_enrich: true}`).
   - Fix option 2: a `kms.customer_keys` list hook that describes each key and keeps CUSTOMER keys
     before the rotation call.
2. **SSM parameter ARN.** DescribeParameters has no ARN, so the node id is the name.
   - A parameter ARN would need the account id in a hook (`ssm.parameter_arn`).
   - The name works as is for CloudFormation and for policies matched by name, so this is optional.
3. **Many stream readers.** `reads-stream` sits on the table with `reverse: true`, and `match`
   returns the first mapping only. With two mappings on one stream, only one edge is drawn.
   - The rule belongs on lambda-event-source (lambda.yaml, not mine):
     `{kind: reads-stream, target: EventSourceArn, match: LatestStreamArn, to: dynamodb-table, style: reference}`.
     The table item has LatestStreamArn under `_Table`, so the match would be `_Table.LatestStreamArn`.
   - Then remove the rule from dynamodb.yaml.
4. **Generic match helper (optional).** Edge `match` returns the first node only. A "match all"
   option would let one stack rule cover several kinds with one name field.
5. **No redaction of sensitive op params.** create-secret.SecretString and put-ssm-parameter.Value
   go to the command line the learner sees. That is fine, because the learner typed them. Nothing
   reads them back, and the chat sees only chat_props. If the chat ever gets the op argv history,
   these two fields need a redaction list.

## SSM document draft (for when Floci lists the APIs)

```yaml
- kind: ssm-document
  service: ssm
  label: SSM Document
  list: {method: list_documents, items: DocumentIdentifiers, params: {Filters: [{Key: Owner, Values: [Self]}]}}
  id: Name
  name: [Name]
  parent: [{kind: region}]
  props: {type: DocumentType, format: DocumentFormat, version: DocumentVersion, schemaVersion: SchemaVersion, platforms: PlatformTypes}
  chat_props: [type, format, version, schemaVersion, platforms]
  view: {role: block, category: management, icon: Res_AWS-Systems-Manager_Documents_48.svg, source: Resource-Icons_07312026/Res_Management-Governance/Res_AWS-Systems-Manager_Documents_48.svg, height: 0.3, order: 121}
```

The icon path exists. The `list.params` constant may need the listing's
`const` support, depending on the schema.

## Tests

- `uv run pytest -q tests/test_registry_sensitive_props.py`: 6 passed.
- The registry loads; check_ops.py: all 24 ops resolve and all 20 contract steps make valid requests.
- Live collect over Floci: 57 nodes, 25 edges, no warnings. Parents are correct. These edges were
  all seen: managed-by (8 kinds across 2 stacks), encrypted-by (table, parameter, secret), alias-of
  (2), reads-stream, rotated-by (2) and execution-role.
- Full `cd server && uv run pytest -q`: **6 failed, 645 passed, 85 deselected**. All 6 failures come
  from the registry growing (my files and the other wave-2 files). None is a defect in these kinds,
  but every one needs a controller-owned fix:
  - `test_app.py::test_registry_endpoint_matches_the_golden_and_the_web_copy`: expected until the
    registry is re-exported.
  - `test_coverage.py::test_the_committed_matrix_is_what_the_generator_writes`: the matrix needs
    regenerating.
  - `test_coverage.py::test_every_catalog_row_gets_the_verdict_its_metadata_supports`: the fixture
    expects `lab-d-ddb` to be `gap` ("no kind of dynamodb"). It is now `ready-with-caveats`, so the
    fixture needs updating.
  - `test_coverage.py::test_the_catalog_summary_counts_verdicts_services_and_reasons`: same cause
    (KeyError on "the registry has no kind of dynamodb").
  - `test_registry.py::test_every_service_failing_raises_for_the_hub_to_judge`:
    - Cause: the test collects the whole registry with a FakeProvider that has only an ec2 client.
      Services that sort before ec2 (backup, cloudformation, cloudwatch, dynamodb) now hit "no fake
      client" first.
    - Fix: the fake should raise TimeoutError for every service.
  - `test_schema.py::test_invalid_lab[over18-known: vpc, subnet]`: the "known:" list of builder kinds
    now starts with backup-vault, cloudformation-stack and others, so the regex should drop the
    order assumption.

## Probe cleanup

Every `pb-data-` resource was deleted:
- two stacks;
- three tables and their global-table records;
- six parameters;
- three secrets and the us-east-1 replica;
- the event source mapping, the function, the role and the function's log group;
- the VPC and KMS key that CloudFormation left behind.

All three customer keys I made are in PendingDeletion (7 days).

## Ready-to-paste scenario function

```python
def build_data_config(c):
    """One of each data/config kind: a KMS key and alias, a DynamoDB table (GSI, stream, TTL, PITR,
    encrypted with the key), String and SecureString parameters, a secret, and a stack that makes
    a parameter (so the parameter is managed-by the stack)."""
    import time

    tags = [{"Key": "lab", "Value": "w2"}]
    kms, ddb, ssm, sm, cfn = c("kms"), c("dynamodb"), c("ssm"), c("secretsmanager"), c("cloudformation")

    key = kms.create_key(Description="w2-data-key", Tags=[{"TagKey": "lab", "TagValue": "w2"}])["KeyMetadata"]
    kms.enable_key_rotation(KeyId=key["KeyId"])
    kms.create_alias(AliasName="alias/w2-data-key", TargetKeyId=key["KeyId"])

    ddb.create_table(
        TableName="w2-orders",
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                              {"AttributeName": "status", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
        GlobalSecondaryIndexes=[{"IndexName": "by-status",
                                 "KeySchema": [{"AttributeName": "status", "KeyType": "HASH"}],
                                 "Projection": {"ProjectionType": "ALL"}}],
        StreamSpecification={"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"},
        SSESpecification={"Enabled": True, "SSEType": "KMS", "KMSMasterKeyId": key["Arn"]},
        Tags=tags,
    )
    ddb.update_time_to_live(TableName="w2-orders",
                            TimeToLiveSpecification={"Enabled": True, "AttributeName": "expiresAt"})
    ddb.update_continuous_backups(TableName="w2-orders",
                                  PointInTimeRecoverySpecification={"PointInTimeRecoveryEnabled": True})

    ssm.put_parameter(Name="/w2/app/db-host", Value="db.internal", Type="String", Tags=tags)
    ssm.put_parameter(Name="/w2/app/api-token", Value="w2-dummy-token", Type="SecureString", KeyId=key["KeyId"], Tags=tags)
    ssm.label_parameter_version(Name="/w2/app/db-host", ParameterVersion=1, Labels=["prod"])

    sm.create_secret(Name="w2-db-password", Description="w2 dummy secret", SecretString="w2-dummy",
                     KmsKeyId=key["KeyId"], Tags=tags)

    template = """AWSTemplateFormatVersion: "2010-09-09"
Description: w2 stack with one parameter
Resources:
  Param:
    Type: AWS::SSM::Parameter
    Properties:
      Name: /w2/cfn/param
      Type: String
      Value: from-cfn
"""
    cfn.create_stack(StackName="w2-stack", TemplateBody=template, Tags=tags)
    for _ in range(50):
        status = cfn.describe_stacks(StackName="w2-stack")["Stacks"][0]["StackStatus"]
        if not status.endswith("_IN_PROGRESS"):
            break
        time.sleep(0.2)
    if status != "CREATE_COMPLETE":
        raise RuntimeError(f"w2-stack ended {status}")
```

No `rotated-by` or `reads-stream` edge is made here, because both need a Lambda function from the
lambda group. If the scenario has one (say `fn_arn`), add
`sm.rotate_secret(SecretId="w2-db-password", RotationLambdaARN=fn_arn, RotationRules={"AutomaticallyAfterDays": 30}, RotateImmediately=False)`
and an event source mapping on the table's LatestStreamArn.

Status: DONE_WITH_CONCERNS
Summary: Added the cloudformation-stack, dynamodb-table, kms-key, kms-alias, ssm-parameter and secretsmanager-secret kinds with ops, contracts, caveats and a sensitive-props test. A live collect over Floci verified them, and the probe resources are cleaned up.
Concerns/Blockers: Six existing tests fail only because the registry grew (golden export, coverage matrix and fixture, a FakeProvider without non-ec2 clients, and a builder-kind order regex); the controller owns those fixes. The ssm-document kind is left out because Floci does not list its APIs as supported. The Run Command caveat and the KMS post-enrich filter are proposals for the controller.
