# Wave 3: messaging kinds (SQS, SNS, Kinesis, Step Functions)

## Outcome

I added five kinds in four new registry files. All of them load.

- Every contract passed on live Floci. Each step was rendered by `catalog.prepare` and run with the aws CLI, and the collector then showed the expected change. Steps took 0.4 to 1.2 s.
- `make_messaging` (below) ran end to end on live Floci with `pb-messaging-` names. A live collect over the result gave no warnings and resolved every parent and edge. All probes are deleted, and a final listing found no `pb-messaging-` resources.
- `labctl coverage --catalog` no longer names sqs, sns, kinesis or stepfunctions in any gap reason.

Files:
- new: `server/src/cloudy_labs/registry/sqs.yaml`, `sns.yaml`, `kinesis.yaml`, `stepfunctions.yaml`
- new: `server/tests/test_registry_messaging.py` (6 tests)
- changed: see "Changes in files I do not own"

## Kinds added

| kind | parent | edges | ops | contract | caveats | view order |
|---|---|---|---|---|---|---|
| `sqs-queue` (id: QueueArn, name: last URL segment) | region | `dead-letter` source queue to DLQ (reverse, from ListDeadLetterSourceQueues); `event-source` queue to lambda-event-source (EventSourceArn) | create-queue, set-queue-attributes, delete-queue | DLQ `ct-dlq` and queue `ct-queue`, then VisibilityTimeout 60 plus a RedrivePolicy to the DLQ, then delete the DLQ; max 5 s | `floci-queue-name-as-url` | 550 |
| `sns-topic` (id: TopicArn, name: last ARN segment) | region | none of its own (subscriptions, rule targets and alarm actions point at it) | create-topic, set-topic-attributes, delete-topic | `ct-topic`, then DisplayName `ct-alerts` | `floci-sns-email-pending`, `floci-sns-no-queue-policy` | 560 |
| `sns-subscription` (label `protocol: endpoint name`) | sns-topic (TopicArn) | `delivers-to` subscription to sqs-queue, lambda-function, lambda-alias or lambda-version (Endpoint) | subscribe (container TopicArn), set-subscription-attributes, unsubscribe | topic `ct-sub-topic` and queue `ct-sub-queue`, subscribe sqs; parent topic; then FilterPolicy, then unsubscribe; max 5 s | none | 561 |
| `kinesis-stream` (id: StreamARN) | region | `event-source` stream to lambda-event-source (EventSourceArn) | create-stream, update-shard-count, delete-stream | `ct-stream` with 1 shard, then 2 shards, then delete | `floci-kinesis-instant-resharding` (prop openShards) | 570 |
| `state-machine` (id: stateMachineArn) | region | `execution-role` to iam-role (roleArn) | create-state-machine, update-state-machine, delete-state-machine | role `ct-sfn-role` (trusts states.amazonaws.com), `ct-state-machine` with a Wait 1 definition, then Wait 2, then delete | `floci-sfn-role-not-assumed` (prop role) | 580 |

Icons:
- SQS Queue, SNS Topic and SNS HTTP-Notification: Resource-Icons_07312026/Res_Application-Integration.
- Kinesis: Arch_Amazon-Kinesis-Data-Streams_48.svg.
- Step Functions: Arch_AWS-Step-Functions_48.svg.

Kinesis has category analytics; the other kinds have category app-integration.

Firehose is not added because no coverage reason names it. The subscription kind was added because labs link a topic to a queue or function through it.

Design notes:
- An SNS email subscription waiting for confirmation is listed with SubscriptionArn `PendingConfirmation`. It is filtered out, since it has no id; the topic's `subscriptionsPending` prop still counts it.
- The SQS queue ops take the queue by its scene label (`ref_by: label, free: true`), because Floci accepts a queue name as QueueUrl (see the caveat). The op note tells the learner that AWS needs the URL from `get-queue-url`.
- The SQS RedrivePolicy is a JSON string that JMESPath cannot read. The dead-letter edge therefore comes from the DLQ side (ListDeadLetterSourceQueues) and is reversed so that it points from the source queue to the DLQ.
- Floci's ListStreams returns only `StreamNames` (no `StreamSummaries`), so the list reshapes it with `StreamNames[].{StreamName: @}`.

## Floci 2.3.0 quirks (each verified live, now caveats)

- SQS accepts a queue name where QueueUrl is expected (`delete-queue --queue-url orders`). It does not accept an ARN there.
- SNS keeps an email subscription pending (PendingConfirmation true, counted in SubscriptionsPending). SQS subscriptions are confirmed at once and receive messages.
- SNS delivers to an SQS subscription even when the queue policy does not allow `sns.amazonaws.com`. AWS drops those messages.
- Kinesis UpdateShardCount takes effect at once, and the stream stays ACTIVE.
- Step Functions does not assume the state machine's role. A role with no policies invoked a Lambda task, and the execution SUCCEEDED.

## Missing APIs

None. Every API used is in `floci-ops-2.3.0.json`.

## Changes in files I do not own

All of these are done.

1. **`registry/hooks.py`**: added `common.last_segment` (append-only, approved by the coordinator). It is the function plus its `HOOKS` entry, and no existing hook changed. It returns the last `sep`-separated segment of a JMESPath field (`as` defaults to `_Name`). SQS ListQueues returns only URLs and SNS ListTopics returns only ARNs, and JMESPath cannot split strings. Unit-tested in test_registry_messaging.py.
2. **`builder/shapes.py`**: added `CLI_RENAMES = {("sns", "Subscribe", "Endpoint"): "--notification-endpoint"}` next to `CLI_BOOLEAN_PAIRS` (approved by the coordinator). `argv()` now looks up the flag there before falling back to `"--" + xform_name(name, "-")`. Without this, the aws CLI reads `--endpoint` as the global `--endpoint-url` and fails with "Invalid endpoint" (awscli customizations/argrename.py). Covered by `test_subscribe_passes_the_endpoint_as_the_cli_names_it`.
3. **Target edge `to:` lists**, as the brief allows:
   - `events.yaml` rule `targets`: added sqs-queue, sns-topic, kinesis-stream and state-machine.
   - `scheduler.yaml` `targets`: added the same four.
   - `cloudwatch.yaml` `alarm-action`: added sns-topic.

   `tests/test_coverage.py` still passes. Its pinned registry only has ec2, rds, s3, lambda and iam, and those kinds do not use these edges.

Needed from the controller (not done):

- **The wave-2 replay now warns for every wave-3 service.** `tests/graph_fixtures.py::wave_2_kinds()` takes every listed kind in the default registry outside the wave-1 services. The wave-2 recording has no fake clients for the new services, so the replay warns "no fake client for sqs" (and likewise for sns, kinesis, stepfunctions and every other wave-3 service), and `test_the_recording_draws_every_kind_the_scenario_built` fails on `g.warnings == []`. The fix belongs to whoever owns the recordings: either re-record with the wave-3 scenario, or pin `wave_2_kinds()` to the kinds the wave-2 recording has.

## Ready-to-paste scenario

`c` maps a service name to a boto3 client on Floci. I tested this on an empty set of these resources with `pb-messaging-` names, collected the result, then deleted everything.

Besides the five messaging kinds, it creates: one iam-role, one lambda-function, two lambda-event-sources (queue and stream), one event-rule with four targets, and one cloudwatch-alarm.

Edges seen in the collect:
- dead-letter
- two delivers-to (to the queue and to the function)
- two event-source (from the queue and from the stream), plus invokes
- four rule targets (queue, topic, stream, state machine)
- alarm-action to the topic
- execution-role

```python
def make_messaging(c):
    """SQS, SNS, Kinesis and Step Functions: one of every kind, linked as AWS links them."""
    import io
    import json
    import zipfile

    tags = {"Name": "w3-messaging"}
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {
        "Service": ["lambda.amazonaws.com", "states.amazonaws.com", "events.amazonaws.com"]}}]}
    role = c("iam").create_role(RoleName="w3-msg-role", AssumeRolePolicyDocument=json.dumps(trust),
                                Tags=[{"Key": k, "Value": v} for k, v in tags.items()])["Role"]["Arn"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("lambda_function.py", "def lambda_handler(event, context):\n    return event\n")
    lam = c("lambda")
    fn = lam.create_function(FunctionName="w3-msg-consumer", Runtime="python3.12", Role=role,
                             Handler="lambda_function.lambda_handler", Code={"ZipFile": buf.getvalue()}, Tags=tags)["FunctionArn"]
    lam.get_waiter("function_active_v2").wait(FunctionName="w3-msg-consumer")

    # SQS: a work queue whose failed messages go to a dead-letter queue; Lambda polls the work queue
    sqs = c("sqs")
    dlq = sqs.create_queue(QueueName="w3-orders-dlq", tags=tags)["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    queue = sqs.create_queue(QueueName="w3-orders", tags=tags, Attributes={
        "VisibilityTimeout": "60",
        "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"})})["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(QueueUrl=queue, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    lam.create_event_source_mapping(EventSourceArn=queue_arn, FunctionName=fn, BatchSize=10)

    # SNS: a topic fanning out to the queue (with a filter policy) and to the function
    sns = c("sns")
    topic = sns.create_topic(Name="w3-order-events", Attributes={"DisplayName": "w3 orders"},
                             Tags=[{"Key": k, "Value": v} for k, v in tags.items()])["TopicArn"]
    sqs.set_queue_attributes(QueueUrl=queue, Attributes={"Policy": json.dumps({"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "sns.amazonaws.com"}, "Action": "sqs:SendMessage",
        "Resource": queue_arn, "Condition": {"ArnEquals": {"aws:SourceArn": topic}}}]})})
    sns.subscribe(TopicArn=topic, Protocol="sqs", Endpoint=queue_arn, ReturnSubscriptionArn=True,
                  Attributes={"FilterPolicy": json.dumps({"type": ["order"]})})
    lam.add_permission(FunctionName="w3-msg-consumer", StatementId="sns", Action="lambda:InvokeFunction",
                       Principal="sns.amazonaws.com", SourceArn=topic)
    sns.subscribe(TopicArn=topic, Protocol="lambda", Endpoint=fn, ReturnSubscriptionArn=True)

    # Kinesis: a stream the function reads from
    kin = c("kinesis")
    kin.create_stream(StreamName="w3-clicks", ShardCount=1)
    kin.get_waiter("stream_exists").wait(StreamName="w3-clicks")
    kin.add_tags_to_stream(StreamName="w3-clicks", Tags=tags)
    stream_arn = kin.describe_stream_summary(StreamName="w3-clicks")["StreamDescriptionSummary"]["StreamARN"]
    lam.create_event_source_mapping(EventSourceArn=stream_arn, FunctionName=fn, StartingPosition="LATEST", BatchSize=100)

    # Step Functions: wait, then call the function
    definition = {"StartAt": "Wait", "States": {
        "Wait": {"Type": "Wait", "Seconds": 1, "Next": "Process"},
        "Process": {"Type": "Task", "Resource": fn, "End": True}}}
    sm = c("stepfunctions").create_state_machine(name="w3-order-flow", definition=json.dumps(definition), roleArn=role,
                                                 tags=[{"key": k, "value": v} for k, v in tags.items()])["stateMachineArn"]

    # Links from older kinds: a rule sends order events to the queue, topic, stream and state machine,
    # and an alarm on the dead-letter queue notifies the topic
    ev = c("events")
    ev.put_rule(Name="w3-orders-rule", EventPattern=json.dumps({"source": ["w3.shop"]}),
                Tags=[{"Key": k, "Value": v} for k, v in tags.items()])
    ev.put_targets(Rule="w3-orders-rule", Targets=[
        {"Id": "queue", "Arn": queue_arn}, {"Id": "topic", "Arn": topic},
        {"Id": "stream", "Arn": stream_arn, "RoleArn": role, "KinesisParameters": {"PartitionKeyPath": "$.id"}},
        {"Id": "flow", "Arn": sm, "RoleArn": role}])
    c("cloudwatch").put_metric_alarm(
        AlarmName="w3-dlq-not-empty", Namespace="AWS/SQS", MetricName="ApproximateNumberOfMessagesVisible",
        Dimensions=[{"Name": "QueueName", "Value": "w3-orders-dlq"}], Statistic="Maximum", Period=60,
        EvaluationPeriods=1, Threshold=1, ComparisonOperator="GreaterThanOrEqualToThreshold",
        AlarmActions=[topic], Tags=[{"Key": k, "Value": v} for k, v in tags.items()])
```

## Coverage before and after

Before, 17 labs named sqs, sns, kinesis or stepfunctions in a gap reason.

After:
- 16 of them are `ready-with-caveats`: lab-034, 035, 037, 042, 058, 065, 066, 089, 093, 094, 103, 105, 106, 109, 110, 112.
- lab-030 is still `blocked` by FSx, but sns is no longer one of its reasons.
- lab-082 is still a `gap`, for "event subscription (dms, docdb, neptune, rds, redshift)". That is an RDS-family event subscription noun, not an SNS kind.

## Tests

- `tests/test_registry_messaging.py`: 6 tests covering:
  - the hook;
  - labels, props and the subscription parent;
  - dead-letter, delivers-to, event-source and invokes edges;
  - the rule, schedule and alarm `to:` lists;
  - subscribe argv;
  - queue ops by scene label.
- With the registry loaded without the in-progress `cognito-identity.yaml`, `tests/test_registry*.py`, `tests/test_builder*.py`, `tests/test_coverage.py` and my file gave 200 passed and 1 failed. The failure is the expected `test_the_committed_matrix_is_what_the_generator_writes`.
- With the full default registry, the builder tests (and my two builder tests) currently fail on another group's file. `cognito-identity.yaml` uses the field `Roles.authenticated`, a key of a MapShape, and `shapes._required` raises `AttributeError: 'MapShape' object has no attribute 'members'`.
- The other failures in the full suite are:
  - the expected `test_registry_endpoint_matches_the_golden_and_the_web_copy` and committed-matrix diffs;
  - the wave-1 and wave-2 replay goldens, which are other groups' changes (route53, rds, s3, ssm) plus the replay warnings described above.

Status: DONE_WITH_CONCERNS
Summary: SQS queue, SNS topic and subscription, Kinesis stream and Step Functions state machine kinds are added, with ops and contracts that pass on live Floci, a verified `make_messaging`, and no coverage gap naming these services. I also added a small hook and a CLI flag rename, both approved by the coordinator.
Concerns/Blockers: The full suite is not clean for reasons outside my files. `cognito-identity.yaml`'s `Roles.authenticated` field crashes `shapes._required` for every builder test. `wave_2_kinds()` makes the wave-2 replay warn for every wave-3 service until the recordings are redone or the kinds are pinned.
