# Wave 2: monitoring and events registry kinds

I added five registry files with ten kinds. All of them load, all 104 ops build, and every contract step prepares with no problems. A live collect of these kinds on Floci 2.3.0 (ap-southeast-2) showed every node, its parent, its props and every edge kind, with no warnings. Every probe resource (prefix `pb-mon-`) has been deleted. The only exception is pushed metric datapoints, which CloudWatch has no API to delete.

Files (all in `server/src/cloudy_labs/registry/`): `cloudwatch.yaml` (95 lines), `logs.yaml` (72), `events.yaml` (107), `scheduler.yaml` (55), `backup.yaml` (126).

## Kinds added

| kind | parent | edges | ops (gesture) | contract | view order |
|---|---|---|---|---|---|
| `cloudwatch-alarm` | region | `watches` to instance (AWS/EC2 InstanceId), lambda-function (AWS/Lambda FunctionName, match), db-instance (AWS/RDS, match), metric-filter (Namespace/MetricName matched against the filter's transformations); `alarm-action` to lambda kinds | put-metric-alarm (create), put-metric-data (attribute), set-alarm-state (attribute) | create ct-alarm, then put-metric-data and set-alarm-state | 400 |
| `cloudwatch-dashboard` | global | none | put-dashboard (create) | create ct-dashboard | 401 |
| `log-group` | region | none | create-log-group (create), put-retention-policy (attribute), put-metric-filter (create, `creates: metric-filter`) | create ct-app-logs, then retention 7 and metric filter ct-errors | 402 |
| `metric-filter` | region (see need 1) | `filter-of` to log-group, matched by region and group name | none of its own (made by put-metric-filter on log-group) | covered by the log-group contract | 403 |
| `event-bus` | region | none | create-event-bus (create, result_id EventBusArn) | create ct-bus | 410 |
| `event-rule` | event-bus (listed per bus, `_Parent`) | `targets` to lambda-function/alias/version, event-bus, log-group; `execution-role` from target RoleArn and rule RoleArn | put-rule (create, container EventBusName by label, result_id RuleArn), put-targets (connect), disable-rule, enable-rule (attribute) | needs bus ct-rule-bus and log group ct-rule-target-logs; create ct-rule in the bus; then put-targets and disable-rule | 411 |
| `schedule` | region | `targets` to lambda kinds and event-bus; `execution-role` | create-schedule (create, result_id ScheduleArn), delete-schedule (delete) | needs role ct-sched-role and bus ct-sched-bus; create ct-schedule; then delete-schedule | 412 |
| `backup-vault` | region | none | create-backup-vault (create, result_id BackupVaultArn), put-backup-vault-lock-configuration, start-backup-job (attribute) | create ct-vault, then lock | 420 |
| `backup-plan` | region | `backs-up-to` to backup-vault (rule vault name, match) | create-backup-plan (create, result_id BackupPlanId) | needs vault ct-plan-vault; create ct-plan | 421 |
| `backup-selection` | backup-plan (listed per plan) | `selects` to s3-bucket, db-instance, db-cluster; `execution-role` | create-backup-selection (create, container BackupPlanId, result_id SelectionId) | needs vault, plan, role and bucket; create ct-sel in the plan | 422 |

Every op has an English `note` and a Vietnamese `title`. None of the `chat_props` carry secrets, values or environment. I checked every icon with `ls` under aws-icon-pkg and referenced it by its `source` path; none was copied. The new edge kinds (`watches`, `alarm-action`, `filter-of`, `targets`, `backs-up-to`, `selects`) all use the `reference` style, and `execution-role` keeps its existing style. No view order collides with another.

## APIs probed on Floci 2.3.0 and the quirks found

All of these calls are in Floci's supported list and I ran each one live.

- **CloudWatch**: PutMetricData, PutMetricAlarm (with Tags), DescribeAlarms, ListMetrics, SetAlarmState, PutDashboard, ListDashboards and GetDashboard all work.
  - An alarm on pushed data reached ALARM after about 70 seconds.
  - Floci publishes no `AWS/*` metrics; ListMetrics shows only custom namespaces.
  - DescribeAlarms never returns CompositeAlarms.
  - Invalid dashboard JSON is rejected with `InvalidParameterInput`.
  - Dashboards are per region in Floci: listing in us-east-1 is empty after a put in ap-southeast-2, even though the ARN has no region.
  - ListTagsForResource answers, but it is not in the supported list, so the registry does not use it.
- **Logs**: CreateLogGroup (with tags), PutRetentionPolicy, PutMetricFilter, DescribeMetricFilters (with and without a group), CreateLogStream, PutLogEvents and ListTagsLogGroup all work.
  - Metric filters do emit metrics: one ERROR line gave AppErrors Sum 1.
  - DescribeLogGroups ignores `logGroupIdentifiers` and returns every group.
  - Floci creates `/aws/rds/instance/<id>/error` for every DB instance even when `EnabledCloudwatchLogsExports` is null.
- **Events**: the default bus exists from the start. CreateEventBus (with Tags) and PutRule (with Tags, both on a custom bus and as a schedule rule on the default bus) work.
  - ListRules and ListTargetsByRule accept the bus ARN as EventBusName, which is what the scoped listing passes.
  - PutTargets accepts a Lambda ARN that does not exist.
  - A log group target receives nothing.
  - An SQS target received a PutEvents event. A rate rule and a scheduler schedule delivered into a bus once a minute, and the bus forwarded to SQS.
  - DisableRule, RemoveTargets, DeleteRule and DeleteEventBus all work.
- **Scheduler**: CreateSchedule (it has no Tags member), ListSchedules (returns only `Target.Arn`), GetSchedule and DeleteSchedule all work.
  - An invalid expression gives a ValidationException.
  - A bus target is accepted without EventBridgeParameters.
  - A role or Lambda that does not exist is accepted.
- **Backup**: these calls all work: CreateBackupVault (BackupVaultTags), CreateBackupPlan (BackupPlanTags), List/GetBackupPlan, Create/List/Get/DeleteBackupSelection, StartBackupJob, ListBackupJobs, ListRecoveryPointsByBackupVault, ListTags, DescribeBackupVault, PutBackupVaultLockConfiguration and DeleteRecoveryPoint.
  - A job reaches COMPLETED in about 6 seconds and NumberOfRecoveryPoints becomes 1. StartBackupJob returns an empty RecoveryPointArn.
  - GetBackupSelection drops ListOfTags.
  - A plan rule naming a vault that does not exist is accepted.
  - Plan schedules never start a job.
  - The vault lock is not enforced: a recovery point and a locked vault (MinRetentionDays 1) were both deleted at once with no error.

## Caveats added

| code | kind | what it says |
|---|---|---|
| `no-service-metrics` | cloudwatch-alarm | Floci publishes no AWS/* metrics, so an alarm on EC2/Lambda/RDS metrics stays INSUFFICIENT_DATA. Push your own data or use set-alarm-state. |
| `floci-regional-dashboards` | cloudwatch-dashboard | Floci keeps each dashboard in the region it was created in. |
| `floci-rds-log-groups` | log-group | Floci creates a `/aws/rds/instance/<id>/error` group for every DB instance. |
| `floci-no-logs-target` | event-rule | A log group target receives no events; other targets do. |
| `floci-target-role-not-assumed` | event-rule, schedule | The target RoleArn is stored, but Floci delivers without assuming it. |
| `floci-schedule-no-jitter` | schedule | A FLEXIBLE window adds no jitter; schedules fire on time, checked about every 10 seconds. |
| `floci-backup-simulated` | backup-vault | Jobs complete and add a recovery point, but no data is copied and nothing can be restored. |
| `floci-backup-plan-no-schedule` | backup-plan | The plan's schedule never starts a job, and a missing vault is accepted. |
| `floci-selection-tags-dropped` | backup-selection | ListOfTags is accepted but never returned. |

I did not add a caveat for the vault lock not being enforced, because I found it during cleanup. It belongs next to `floci-backup-simulated` if the controller wants it.

## Hook and schema needs (not done: these files are outside my ownership)

1. **ParentRule by match.** A metric filter names its group only by `logGroupName`, and DescribeLogGroups ignores `logGroupIdentifiers`, so an enrich cannot fetch the ARN. A `match` (or lookup) on ParentRule would let metric-filter nest in its log group instead of the region. For now it sits in the region with a `filter-of` edge.
2. **`_with_parents` should add `listing.scope.parent_kind`.** If a lab lists only `event-rule`, `metric-filter` or `backup-selection`, their scope kinds (event-bus, log-group, backup-plan) are not collected, and the scoped listing has nothing to iterate.
3. **A JSON-string parse hook.** Dashboard bodies and rule event patterns are JSON strings. Parsing them would give a widget count and structured `eventPattern` props. Today `eventPattern` is the raw string and the dashboard has only `size`.
4. **Region-aware `match` edges.** The `match` edges from alarm to lambda-function, alarm to metric-filter and backup-plan to backup-vault compare names only. In a multi-region lab they could link across regions. The `filter-of` edge already folds `_Region` into both sides; the others cannot, because the far side's field is a bare name.
5. **Dotted `expect.label`.** create-backup-plan and create-backup-selection take their names at `BackupPlan.BackupPlanName` and `BackupSelection.SelectionName`. Expectations only accept a top-level param, so both ops rely on `result_id` and have no `expect`. Practice mode then falls back to `{after: 0}` for them.
6. **Sanitizer name rule and log group names.** `builder/sanitize.py` treats `logGroupName` (and `BackupPlan.BackupPlanName`, `BackupSelection.SelectionName`, `filterName`) as a name and requires `[A-Za-z0-9._-]{1,64}`. That refuses the usual `/app/web` log group names, which allow `/` and `#` and are up to 512 characters long. I changed the contracts to `ct-app-logs` and `ct-rule-target-logs`, and the create-log-group note says so. Log groups need a per-field exception, or a looser rule for `logGroupName`.
7. **Auto-tagging.** The server tags only members called `Tags` (a Key/Value list) or `tags` (a map). Backup uses `BackupVaultTags` and `BackupPlanTags`, and CreateSchedule has no tags at all. So builder-made vaults, plans and schedules carry no lab tag.
8. **More edge targets later.** SQS was a working rule target on Floci. Once `sqs-queue` and `sns-topic` kinds exist, add them to the `to` lists of the event-rule and schedule `targets` edges and the alarm `alarm-action` edge.
9. **Tests that depend on service order.** These fail because of file and service order, and fail the same way for any new service that sorts before `ec2`:
   - `test_registry.py::test_every_service_failing_raises_for_the_hub_to_judge`: collect re-raises the first failing service in sorted order (`collector.py:402`). That is now `backup` (the fake provider raises AssertionError for it), not `ec2`'s TimeoutError. The other agents' `cloudformation`, `dynamodb` and `efs` cause the same failure.
   - `test_schema.py::test_invalid_lab[over18-known: vpc, subnet]`: the "known:" list follows yaml file order, so it now starts with `backup-vault, ...` and not `vpc, subnet`.

## Tests

- `uv run pytest -q tests/test_registry.py tests/test_builder_catalog.py tests/test_builder_shapes.py tests/test_coverage.py`: 61 passed and 4 failed.
- Full `uv run pytest -q`: 645 passed, 6 failed, 85 deselected (docker tests).

The six failures:

- **Expected golden differences:**
  - `test_app.py::test_registry_endpoint_matches_the_golden_and_the_web_copy`: `web/src/registry/registry.json` needs regenerating.
  - `test_coverage.py::test_the_committed_matrix_is_what_the_generator_writes`: `docs/coverage.md` needs `labctl coverage --matrix`.
- **Order fragility** (need 9): `test_registry.py::test_every_service_failing_raises_for_the_hub_to_judge` and `test_schema.py::test_invalid_lab[over18-...]`.
- **Not caused by these files:**
  - `test_coverage.py::test_every_catalog_row_gets_the_verdict_its_metadata_supports`
  - `test_coverage.py::test_the_catalog_summary_counts_verdicts_services_and_reasons`

  Both expect "the registry has no kind of dynamodb". `dynamodb.yaml` from the data/config group now exists, so the fixture's `lab-d-ddb` row became ready-with-caveats.

## Build function

I ran this function live on Floci with the names switched to `pb-mon-`, then deleted everything it made.
- The collect afterwards showed all ten new kinds plus the role and the bucket, with no warnings.
- Every edge kind appeared: `watches` (alarm to metric filter), `filter-of`, `targets` (rule to log group, rule to bus, schedule to bus), `execution-role` (rule, schedule, selection), `backs-up-to` and `selects`.
- `c(service)` returns a boto3 client for the lab region.

```python
def build_monitoring_events(c):
    """CloudWatch, Logs, EventBridge, Scheduler and Backup: one of every kind, linked to each other."""
    import json

    region = c("sts").meta.region_name
    tags = [{"Key": "Name", "Value": "w2-monitoring"}]
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {
        "Service": ["scheduler.amazonaws.com", "events.amazonaws.com", "backup.amazonaws.com"]}}]}
    role = c("iam").create_role(RoleName="w2-mon-role", AssumeRolePolicyDocument=json.dumps(trust), Tags=tags)["Role"]["Arn"]

    # CloudWatch Logs: a group with a metric filter that turns ERROR lines into w2/Logs AppErrors
    logs = c("logs")
    logs.create_log_group(logGroupName="w2-app-logs", tags={"Name": "w2-app-logs"})
    logs.put_retention_policy(logGroupName="w2-app-logs", retentionInDays=7)
    logs.put_metric_filter(logGroupName="w2-app-logs", filterName="w2-errors", filterPattern="ERROR",
                           metricTransformations=[{"metricName": "AppErrors", "metricNamespace": "w2/Logs",
                                                   "metricValue": "1", "defaultValue": 0}])
    logs.create_log_group(logGroupName="w2-rule-target", tags={"Name": "w2-rule-target"})
    lg_target = next(g["arn"].removesuffix(":*") for g in logs.describe_log_groups(logGroupNamePrefix="w2-rule-target")["logGroups"])

    # CloudWatch: an alarm on the filter's metric (it watches the filter) and a dashboard
    cw = c("cloudwatch")
    cw.put_metric_data(Namespace="w2/Logs", MetricData=[{"MetricName": "AppErrors", "Value": 0, "Unit": "Count"}])
    cw.put_metric_alarm(AlarmName="w2-errors-alarm", Namespace="w2/Logs", MetricName="AppErrors", Statistic="Sum",
                        Period=60, EvaluationPeriods=1, Threshold=1, ComparisonOperator="GreaterThanOrEqualToThreshold",
                        TreatMissingData="notBreaching", AlarmDescription="errors in w2-app-logs", Tags=tags)
    cw.put_dashboard(DashboardName="w2-dashboard", DashboardBody=json.dumps({"widgets": [{
        "type": "metric", "x": 0, "y": 0, "width": 12, "height": 6,
        "properties": {"metrics": [["w2/Logs", "AppErrors"]], "region": region, "title": "w2 errors"}}]}))

    # EventBridge: a custom bus, a rule on it with a log group target, and a schedule rule on the default bus
    ev = c("events")
    bus = ev.create_event_bus(Name="w2-bus", Description="w2 app events", Tags=tags)["EventBusArn"]
    ev.put_rule(Name="w2-orders", EventBusName="w2-bus", EventPattern=json.dumps({"source": ["w2.app"]}),
                Description="w2 orders", Tags=tags)
    ev.put_targets(Rule="w2-orders", EventBusName="w2-bus", Targets=[{"Id": "logs", "Arn": lg_target}])
    ev.put_rule(Name="w2-hourly", ScheduleExpression="rate(1 hour)", State="DISABLED", Tags=tags)
    ev.put_targets(Rule="w2-hourly", Targets=[{"Id": "bus", "Arn": bus, "RoleArn": role}])

    # EventBridge Scheduler: CreateSchedule has no Tags member
    c("scheduler").create_schedule(Name="w2-schedule", ScheduleExpression="rate(1 hour)", State="DISABLED",
                                   FlexibleTimeWindow={"Mode": "OFF"}, Description="w2 hourly ping",
                                   Target={"Arn": bus, "RoleArn": role, "Input": json.dumps({"source": "w2.app"})})

    # AWS Backup: a vault, a plan whose rule names it, and a selection of one bucket
    bk = c("backup")
    c("s3").create_bucket(Bucket="w2-backup-src", CreateBucketConfiguration={"LocationConstraint": region})
    c("s3").put_bucket_tagging(Bucket="w2-backup-src", Tagging={"TagSet": tags})
    bk.create_backup_vault(BackupVaultName="w2-vault", BackupVaultTags={"Name": "w2-vault"})
    plan = bk.create_backup_plan(BackupPlan={"BackupPlanName": "w2-plan", "Rules": [{
        "RuleName": "daily", "TargetBackupVaultName": "w2-vault", "ScheduleExpression": "cron(0 5 ? * * *)",
        "Lifecycle": {"DeleteAfterDays": 7}}]}, BackupPlanTags={"Name": "w2-plan"})["BackupPlanId"]
    bk.create_backup_selection(BackupPlanId=plan, BackupSelection={
        "SelectionName": "w2-selection", "IamRoleArn": role, "Resources": ["arn:aws:s3:::w2-backup-src"]})
    bk.start_backup_job(BackupVaultName="w2-vault", ResourceArn="arn:aws:s3:::w2-backup-src", IamRoleArn=role)
```

Notes for the recorder:
- The function also creates one `iam-role` and one `s3-bucket`, so record those kinds too, or the `execution-role` and `selects` edges have no far end.
- The job started at the end completes about 6 seconds later. Wait before recording if the fixture should show `recoveryPoints: 1`.
- Metric data is pushed once, so the alarm stays OK (Sum 0 is below the threshold of 1).

Status: DONE_WITH_CONCERNS
Summary: I added ten kinds in five registry files, probed every API live, and verified them with a live collect and a working build function. All probe resources were cleaned up. The registry and builder tests pass apart from the golden files, two tests broken by service order, and two dynamodb coverage tests owned by another group.
Concerns/Blockers: These need someone else to act: the test fixes for service order (need 9), the sanitizer refusing `/` in log group names (need 6), lab tags for Backup and Scheduler (need 7), and the parent and scope hook needs (needs 1, 2 and 5). The `registry.json` and `docs/coverage.md` golden files need regenerating.
