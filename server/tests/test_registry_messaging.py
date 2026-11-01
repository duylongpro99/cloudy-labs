"""SQS, SNS, Kinesis and Step Functions kinds: names read from URLs and ARNs, links between queues,
topics, streams and functions, and the builder commands their contracts run."""
from datetime import datetime, timezone

from cloudy_labs.builder.catalog import op_named, prepare
from cloudy_labs.graph.collector import CollectContext, build_graph
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.registry import default_registry
from cloudy_labs.registry.hooks import HOOKS

REGION = "ap-southeast-2"
ACCOUNT = "000000000000"
QUEUE = f"arn:aws:sqs:{REGION}:{ACCOUNT}:orders"
DLQ = f"arn:aws:sqs:{REGION}:{ACCOUNT}:orders-dlq"
TOPIC = f"arn:aws:sns:{REGION}:{ACCOUNT}:order-events"
STREAM = f"arn:aws:kinesis:{REGION}:{ACCOUNT}:stream/clicks"
FUNCTION = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:consumer"


def url(name: str) -> str:
    return f"http://localhost:4566/{ACCOUNT}/{name}"


def enriched(kind: str, item: dict) -> dict:
    """The item as the collector holds it after the kind's hook enrichments."""
    for e in default_registry().by_kind[kind].enrich:
        if e.hook:
            item = {**item, **HOOKS[e.hook](None, None, item, e.args)}
    return item


def graph() -> ResourceGraph:
    raw = {
        "sqs-queue": [
            enriched("sqs-queue", {"QueueUrl": url("orders"), "_Attr": {"QueueArn": QUEUE, "VisibilityTimeout": "60"}}),
            enriched("sqs-queue", {"QueueUrl": url("orders-dlq"), "_Attr": {"QueueArn": DLQ, "FifoQueue": "false"},
                                   "_Sources": [url("orders")]}),
        ],
        "sns-topic": [enriched("sns-topic", {"TopicArn": TOPIC, "_Attr": {"DisplayName": "Orders"}})],
        "sns-subscription": [enriched("sns-subscription", {
            "SubscriptionArn": f"{TOPIC}:1111", "TopicArn": TOPIC, "Protocol": "sqs", "Endpoint": QUEUE,
            "_Attr": {"FilterPolicy": '{"type": ["order"]}'}})],
        "kinesis-stream": [{"StreamName": "clicks", "_Summary": {"StreamARN": STREAM, "OpenShardCount": 2}}],
        "lambda-function": [{"FunctionArn": FUNCTION, "FunctionName": "consumer"}],
        "lambda-event-source": [
            {"EventSourceMappingArn": "esm-queue", "UUID": "esm-queue", "EventSourceArn": QUEUE, "FunctionArn": FUNCTION},
            {"EventSourceMappingArn": "esm-stream", "UUID": "esm-stream", "EventSourceArn": STREAM, "FunctionArn": FUNCTION},
        ],
    }
    ctx = CollectContext(clients=lambda s: None, now=datetime(2026, 1, 1, tzinfo=timezone.utc), ports=lambda: {}, region=REGION)
    return build_graph(default_registry(), raw, ctx, regions=[REGION], account=ACCOUNT)


def test_the_name_is_the_last_segment_of_an_arn_or_url():
    hook = HOOKS["common.last_segment"]
    assert hook(None, None, {"QueueUrl": url("orders.fifo")}, {"field": "QueueUrl", "sep": "/"}) == {"_Name": "orders.fifo"}
    assert hook(None, None, {"TopicArn": TOPIC}, {"field": "TopicArn", "sep": ":", "as": "_T"}) == {"_T": "order-events"}
    assert hook(None, None, {"Endpoint": "ops@example.com"}, {"field": "Endpoint"}) == {"_Name": "ops@example.com"}
    assert hook(None, None, {}, {"field": "TopicArn"}) == {}


def test_queues_and_topics_are_named_and_subscriptions_sit_in_their_topic():
    g = graph()
    nodes = {n.id: n for n in g.nodes}
    parents = {c.child: c.parent for c in g.contains}
    assert nodes[QUEUE].label == "orders" and nodes[QUEUE].props["visibilityTimeout"] == "60"
    assert nodes[TOPIC].label == "order-events" and nodes[TOPIC].props["displayName"] == "Orders"
    assert nodes[f"{TOPIC}:1111"].label == "sqs: orders" and parents[f"{TOPIC}:1111"] == TOPIC
    assert nodes[STREAM].label == "clicks" and nodes[STREAM].props["openShards"] == 2


def test_queues_and_streams_link_to_their_dead_letter_queue_subscribers_and_consumers():
    edges = {(e.kind, e.from_, e.to) for e in graph().edges}
    assert ("dead-letter", QUEUE, DLQ) in edges
    assert ("delivers-to", f"{TOPIC}:1111", QUEUE) in edges
    assert ("event-source", QUEUE, "esm-queue") in edges and ("event-source", STREAM, "esm-stream") in edges
    assert ("invokes", "esm-queue", FUNCTION) in edges


def test_rules_schedules_and_alarms_may_point_at_the_messaging_kinds():
    reg = default_registry()
    rule = next(e for e in reg.by_kind["event-rule"].edges if e.kind == "targets")
    schedule = next(e for e in reg.by_kind["schedule"].edges if e.kind == "targets")
    alarm = next(e for e in reg.by_kind["cloudwatch-alarm"].edges if e.kind == "alarm-action")
    assert {"sqs-queue", "sns-topic", "kinesis-stream", "state-machine"} <= set(rule.to) & set(schedule.to)
    assert "sns-topic" in alarm.to


def test_subscribe_passes_the_endpoint_as_the_cli_names_it():
    g = graph()
    prepared = prepare(op_named("subscribe"), {"TopicArn": TOPIC, "Protocol": "sqs", "Endpoint": QUEUE},
                       graph=g, azs=[], choices={}, tags={})
    assert prepared.problems == []
    argv = prepared.argv
    assert argv[argv.index("--notification-endpoint") + 1] == QUEUE and "--endpoint" not in argv
    assert "--return-subscription-arn" in argv


def test_queue_ops_take_the_queue_by_its_name_in_the_scene():
    g = graph()
    prepared = prepare(op_named("set-queue-attributes"), {"QueueUrl": "orders", "Attributes": '{"VisibilityTimeout": "60"}'},
                       graph=g, azs=[], choices={}, tags={})
    assert prepared.problems == [] and prepared.target == QUEUE
    deleted = prepare(op_named("delete-queue"), {"QueueUrl": "orders"}, graph=g, azs=[], choices={}, tags={})
    assert deleted.problems == [] and deleted.target == QUEUE
    missing = prepare(op_named("delete-queue"), {"QueueUrl": "other"}, graph=g, azs=[], choices={}, tags={})
    assert [p.field for p in missing.problems] == ["QueueUrl"]
