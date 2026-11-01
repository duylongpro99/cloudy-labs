"""Checks for Lab 62. The log group, stream, metric filter and alarm are found by the names the lab
gives them; the SNS topic is whichever topic the alarm notifies.

The filter's pattern is judged by what it matches, through TestMetricFilter on lines of our own, so
any pattern with the same effect passes. Floci keeps no alarm history, so an alarm that fired and
went back to OK is recognised by the metric itself: a minute whose sum passed the threshold.
"""

from datetime import datetime, timedelta, timezone

from cloudy_labs.checks import CheckContext, CheckResult

GROUP = "/aws/app/lab62-payment-service"
STREAM = "payment-api-node-01"
FILTER = "lab62-extract-app-errors"
ALARM = "lab62-critical-app-errors-alarm"
NAMESPACE = "MyApp/Production"
METRIC = "ApplicationErrorCount"
# Lines of our own, not the lab's: which of them a correct pattern matches.
MATCH = ["2026-01-01T00:00:00Z [ERROR] card declined by issuer",
         "2026-01-01T00:00:01Z [CRITICAL] queue consumer stopped",
         "2026-01-01T00:00:02Z [WARN] IllegalStateException while closing a socket"]
SKIP = ["2026-01-01T00:00:03Z [INFO] health check passed",
        "2026-01-01T00:00:04Z [WARN] slow response from the ledger"]
ERROR_WORDS = ("ERROR", "CRITICAL", "Exception")


def _group(ctx: CheckContext) -> dict | None:
    groups = ctx.client("logs").describe_log_groups(logGroupNamePrefix=GROUP)["logGroups"]
    return next((g for g in groups if g["logGroupName"] == GROUP), None)


def _group_id(group: dict) -> str:
    return group.get("logGroupArn") or group["arn"].removesuffix(":*")


def _filter(ctx: CheckContext) -> dict | None:
    logs = ctx.client("logs")
    try:
        filters = logs.describe_metric_filters(logGroupName=GROUP, filterNamePrefix=FILTER)["metricFilters"]
    except logs.exceptions.ResourceNotFoundException:  # no log group yet
        return None
    return next((f for f in filters if f["filterName"] == FILTER), None)


def _filter_id(ctx: CheckContext) -> str:
    # The collector's id for a metric filter: its region, log group and name.
    return f"metric-filter:{ctx.client('logs').meta.region_name}:{GROUP}:{FILTER}"


def _alarm(ctx: CheckContext) -> dict | None:
    alarms = ctx.client("cloudwatch").describe_alarms(AlarmNames=[ALARM])["MetricAlarms"]
    return alarms[0] if alarms else None


def log_group_retention(ctx: CheckContext, days: list[int]) -> CheckResult:
    group = _group(ctx)
    if group is None:
        return CheckResult(False, f"no log group named {GROUP} yet")
    ids = [_group_id(group)]
    kept = group.get("retentionInDays")
    if kept not in days:
        return CheckResult(False, f"{GROUP} keeps events {'forever' if kept is None else f'{kept} days'}; "
                                  f"the lab asks for {' or '.join(map(str, days))} days", ids)
    return CheckResult(True, f"{GROUP} keeps events for {kept} days", ids)


def log_stream_exists(ctx: CheckContext) -> CheckResult:
    group = _group(ctx)
    if group is None:
        return CheckResult(False, f"no log group named {GROUP} yet")
    ids = [_group_id(group)]
    streams = ctx.client("logs").describe_log_streams(logGroupName=GROUP, logStreamNamePrefix=STREAM)["logStreams"]
    if not any(s["logStreamName"] == STREAM for s in streams):
        return CheckResult(False, f"{GROUP} has no stream named {STREAM} yet", ids)
    return CheckResult(True, f"{GROUP} holds the stream {STREAM}", ids)


def stream_has_events(ctx: CheckContext) -> CheckResult:
    group = _group(ctx)
    if group is None:
        return CheckResult(False, f"no log group named {GROUP} yet")
    ids = [_group_id(group)]
    logs = ctx.client("logs")
    try:
        events = logs.get_log_events(logGroupName=GROUP, logStreamName=STREAM, startFromHead=True, limit=1000)["events"]
    except logs.exceptions.ResourceNotFoundException:
        return CheckResult(False, f"{GROUP} has no stream named {STREAM} yet", ids)
    if not events:
        return CheckResult(False, f"{STREAM} holds no log events yet", ids)
    errors = sum(1 for e in events if any(w in e["message"] for w in ERROR_WORDS))
    if not errors:
        return CheckResult(False, f"{STREAM} holds {len(events)} event(s) but no ERROR, CRITICAL or Exception line", ids)
    return CheckResult(True, f"{STREAM} holds {len(events)} event(s), {errors} of them errors", ids)


def filter_pattern(ctx: CheckContext) -> CheckResult:
    found = _filter(ctx)
    if found is None:
        return CheckResult(False, f"{GROUP} has no metric filter named {FILTER} yet")
    ids = [_filter_id(ctx)]
    lines = MATCH + SKIP
    matches = ctx.client("logs").test_metric_filter(filterPattern=found.get("filterPattern", ""), logEventMessages=lines)["matches"]
    hit = {m["eventNumber"] for m in matches}
    missed = [w for n, w in enumerate(ERROR_WORDS, 1) if n not in hit]
    wrong = [n for n in range(len(MATCH) + 1, len(lines) + 1) if n in hit]
    if missed:
        return CheckResult(False, f"{FILTER} misses lines holding {', '.join(missed)}", ids)
    if wrong:
        return CheckResult(False, f"{FILTER} also matches INFO or WARN lines without an error word", ids)
    return CheckResult(True, f"{FILTER} matches ERROR, CRITICAL and Exception lines only", ids)


def filter_metric(ctx: CheckContext) -> CheckResult:
    found = _filter(ctx)
    if found is None:
        return CheckResult(False, f"{GROUP} has no metric filter named {FILTER} yet")
    ids = [_filter_id(ctx)]
    t = next(iter(found.get("metricTransformations") or []), {})
    if (t.get("metricNamespace"), t.get("metricName")) != (NAMESPACE, METRIC):
        return CheckResult(False, f"{FILTER} writes {t.get('metricNamespace')} {t.get('metricName')}; "
                                  f"the lab asks for {NAMESPACE} {METRIC}", ids)
    if t.get("metricValue") != "1":
        return CheckResult(False, f"{FILTER} counts {t.get('metricValue')} per match; the lab asks for 1", ids)
    if t.get("defaultValue") is None or float(t["defaultValue"]) != 0:
        return CheckResult(False, f"{FILTER} has no default value of 0, so quiet minutes report no data", ids)
    if t.get("unit") != "Count":
        return CheckResult(False, f"{FILTER} reports in {t.get('unit') or 'no unit'}; the lab asks for Count", ids)
    return CheckResult(True, f"{FILTER} counts 1 per match into {NAMESPACE} {METRIC}, 0 by default", ids)


def alarm_settings(ctx: CheckContext, threshold: float) -> CheckResult:
    alarm = _alarm(ctx)
    if alarm is None:
        return CheckResult(False, f"no alarm named {ALARM} yet")
    ids = [alarm["AlarmArn"]]
    if (alarm.get("Namespace"), alarm.get("MetricName")) != (NAMESPACE, METRIC):
        return CheckResult(False, f"{ALARM} watches {alarm.get('Namespace')} {alarm.get('MetricName')}, not {NAMESPACE} {METRIC}", ids)
    wrong = []
    if alarm.get("Statistic") != "Sum":
        wrong.append(f"statistic {alarm.get('Statistic')} (Sum)")
    if alarm.get("Period") != 60:
        wrong.append(f"period {alarm.get('Period')} s (60)")
    if alarm.get("ComparisonOperator") != "GreaterThanThreshold" or float(alarm.get("Threshold", -1)) != threshold:
        wrong.append(f"{alarm.get('ComparisonOperator')} {alarm.get('Threshold')} (GreaterThanThreshold {threshold:g})")
    if (alarm.get("EvaluationPeriods"), alarm.get("DatapointsToAlarm", alarm.get("EvaluationPeriods"))) != (1, 1):
        wrong.append(f"{alarm.get('DatapointsToAlarm')} of {alarm.get('EvaluationPeriods')} datapoints (1 of 1)")
    if wrong:
        return CheckResult(False, f"{ALARM} has {'; '.join(wrong)}", ids)
    return CheckResult(True, f"{ALARM} fires when {METRIC} sums above {threshold:g} in a minute", ids)


def alarm_notifies(ctx: CheckContext) -> CheckResult:
    alarm = _alarm(ctx)
    if alarm is None:
        return CheckResult(False, f"no alarm named {ALARM} yet")
    topics = [a for a in alarm.get("AlarmActions") or [] if a.startswith("arn:aws:sns:")]
    if not topics:
        return CheckResult(False, f"{ALARM} notifies no SNS topic when it goes into alarm", [alarm["AlarmArn"]])
    sns = ctx.client("sns")
    for arn in topics:
        try:
            sns.get_topic_attributes(TopicArn=arn)
        except sns.exceptions.NotFoundException:
            continue
        return CheckResult(True, f"{ALARM} notifies the topic {arn.rsplit(':', 1)[-1]}", [arn, alarm["AlarmArn"]])
    return CheckResult(False, f"{ALARM} notifies a topic that does not exist", [alarm["AlarmArn"]])


def alarm_fired(ctx: CheckContext, threshold: float) -> CheckResult:
    alarm = _alarm(ctx)
    if alarm is None:
        return CheckResult(False, f"no alarm named {ALARM} yet")
    ids = [alarm["AlarmArn"]]
    if alarm.get("StateValue") == "ALARM":
        return CheckResult(True, f"{ALARM} is in ALARM", ids)
    now = datetime.now(timezone.utc)
    points = ctx.client("cloudwatch").get_metric_statistics(
        Namespace=NAMESPACE, MetricName=METRIC, StartTime=now - timedelta(hours=3), EndTime=now + timedelta(minutes=1),
        Period=60, Statistics=["Sum"])["Datapoints"]
    peak = max((p["Sum"] for p in points), default=0)
    if peak > threshold:
        return CheckResult(True, f"{METRIC} reached {peak:g} in a minute; {ALARM} is {alarm.get('StateValue')} now", ids)
    return CheckResult(False, f"{ALARM} is {alarm.get('StateValue')} and {METRIC} has peaked at {peak:g} a minute; "
                              f"send more than {threshold:g} error lines at once", ids)
