"""Checks for Lab 93. The two queues are found by the names the lab gives them; the node id of a
queue is its ARN.

A message that reached the dead-letter queue is either still there or was moved back by a redrive,
so the redrive's move task counts as proof that the message dead-lettered.
"""

import json

from cloudy_labs.checks import CheckContext, CheckResult

MAIN = "lab93-orders-main-queue"
DLQ = "lab93-orders-dlq"


def _attributes(ctx: CheckContext, name: str) -> dict | None:
    sqs = ctx.client("sqs")
    try:
        url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
    except sqs.exceptions.QueueDoesNotExist:
        return None
    return sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"]


def _missing(name: str) -> CheckResult:
    return CheckResult(False, f"no queue named {name} yet")


def _moves(ctx: CheckContext, dlq_arn: str) -> list[dict]:
    return ctx.client("sqs").list_message_move_tasks(SourceArn=dlq_arn).get("Results") or []


def queue_settings(ctx: CheckContext, name: str, visibility: int, retention: int) -> CheckResult:
    attrs = _attributes(ctx, name)
    if attrs is None:
        return _missing(name)
    ids = [attrs["QueueArn"]]
    if attrs.get("FifoQueue") == "true":
        return CheckResult(False, f"{name} is a FIFO queue; the lab asks for a standard one", ids)
    got = int(attrs.get("VisibilityTimeout", 0)), int(attrs.get("MessageRetentionPeriod", 0))
    if got != (visibility, retention):
        return CheckResult(False, f"{name} has a {got[0]} s visibility timeout and {got[1]} s of retention; "
                                  f"the lab asks for {visibility} s and {retention} s", ids)
    return CheckResult(True, f"{name}: {visibility} s visibility timeout, {retention // 86400} days of retention", ids)


def redrive_policy(ctx: CheckContext, max_receives: int) -> CheckResult:
    main, dlq = _attributes(ctx, MAIN), _attributes(ctx, DLQ)
    if main is None:
        return _missing(MAIN)
    if dlq is None:
        return _missing(DLQ)
    ids = [main["QueueArn"], dlq["QueueArn"]]
    policy = json.loads(main.get("RedrivePolicy") or "{}")
    if policy.get("deadLetterTargetArn") != dlq["QueueArn"]:
        return CheckResult(False, f"{MAIN} has no redrive policy pointing at {DLQ}", ids)
    if int(policy.get("maxReceiveCount", 0)) != max_receives:
        return CheckResult(False, f"{MAIN} dead-letters after {policy.get('maxReceiveCount')} receives; "
                                  f"the lab asks for {max_receives}", ids)
    return CheckResult(True, f"{MAIN} sends a message to {DLQ} after {max_receives} receives", ids)


def message_dead_lettered(ctx: CheckContext) -> CheckResult:
    dlq = _attributes(ctx, DLQ)
    if dlq is None:
        return _missing(DLQ)
    ids = [dlq["QueueArn"]]
    waiting = int(dlq.get("ApproximateNumberOfMessages", 0)) + int(dlq.get("ApproximateNumberOfMessagesNotVisible", 0))
    if waiting:
        return CheckResult(True, f"{DLQ} holds {waiting} message(s)", ids)
    if any(t.get("ApproximateNumberOfMessagesMoved", 0) for t in _moves(ctx, dlq["QueueArn"])):
        return CheckResult(True, f"{DLQ} held a message, redriven since", ids)
    return CheckResult(False, f"{DLQ} has never held a message: receive one from {MAIN} until the "
                              "redrive policy's limit, without deleting it", ids)


def message_redriven(ctx: CheckContext) -> CheckResult:
    main, dlq = _attributes(ctx, MAIN), _attributes(ctx, DLQ)
    if main is None:
        return _missing(MAIN)
    if dlq is None:
        return _missing(DLQ)
    ids = [main["QueueArn"], dlq["QueueArn"]]
    # No DestinationArn, or the main queue's: both send messages back to the main queue.
    back = [t for t in _moves(ctx, dlq["QueueArn"]) if t.get("DestinationArn") in (None, main["QueueArn"])]
    done = [t for t in back if t.get("Status") == "COMPLETED" and t.get("ApproximateNumberOfMessagesMoved", 0)]
    if done:
        return CheckResult(True, f"a redrive moved {done[0]['ApproximateNumberOfMessagesMoved']} message(s) back to {MAIN}", ids)
    if back:
        return CheckResult(False, f"the redrive from {DLQ} is {back[0].get('Status')} and has moved nothing yet", ids)
    return CheckResult(False, f"no redrive from {DLQ} back to {MAIN} yet", ids)
