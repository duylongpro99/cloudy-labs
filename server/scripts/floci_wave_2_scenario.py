"""The second-wave scenario: one of every monitoring, events, data, config and network kind, linked
to each other where AWS links them. `record-floci-fixtures.py build-wave-2` runs it on an empty Floci.

Every function takes `c`, a function from service name to a boto3 client pointed at Floci.
Values put in parameters and secrets are dummies; the collector reads only their metadata.
"""

from __future__ import annotations

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

def build_network(c):
    """EFS, ELBv2, Auto Scaling and Route 53: one of every kind in a VPC of its own, linked to each other."""
    region = c("sts").meta.region_name

    def tags(name):
        return [{"Key": "Name", "Value": name}]

    def spec(name, kind):
        return [{"ResourceType": kind, "Tags": tags(name)}]

    # A VPC with a subnet in each of two AZs and a security group for HTTP and NFS from inside it
    ec2 = c("ec2")
    vpc = ec2.create_vpc(CidrBlock="10.91.0.0/16", TagSpecifications=spec("w2-net-vpc", "vpc"))["Vpc"]["VpcId"]
    a = ec2.create_subnet(VpcId=vpc, CidrBlock="10.91.1.0/24", AvailabilityZone=f"{region}a",
                          TagSpecifications=spec("w2-net-a", "subnet"))["Subnet"]["SubnetId"]
    b = ec2.create_subnet(VpcId=vpc, CidrBlock="10.91.2.0/24", AvailabilityZone=f"{region}b",
                          TagSpecifications=spec("w2-net-b", "subnet"))["Subnet"]["SubnetId"]
    sg = ec2.create_security_group(GroupName="w2-net-sg", Description="w2 web and nfs", VpcId=vpc,
                                   TagSpecifications=spec("w2-net-sg", "security-group"))["GroupId"]
    ec2.authorize_security_group_ingress(GroupId=sg, IpPermissions=[
        {"IpProtocol": "tcp", "FromPort": port, "ToPort": port, "IpRanges": [{"CidrIp": "10.91.0.0/16"}]}
        for port in (80, 2049)])
    image = ec2.describe_images()["Images"][0]["ImageId"]
    lt = ec2.create_launch_template(LaunchTemplateName="w2-lt", LaunchTemplateData={
        "ImageId": image, "InstanceType": "t3.micro", "SecurityGroupIds": [sg]},
        TagSpecifications=spec("w2-lt", "launch-template"))["LaunchTemplate"]["LaunchTemplateId"]

    # EFS: a file system with a lifecycle policy, a mount target in subnet a and an access point
    efs = c("efs")
    fs = efs.create_file_system(CreationToken="w2-efs", PerformanceMode="generalPurpose", ThroughputMode="elastic",
                                Encrypted=True, Tags=tags("w2-efs"))["FileSystemId"]
    efs.put_lifecycle_configuration(FileSystemId=fs, LifecyclePolicies=[{"TransitionToIA": "AFTER_30_DAYS"}])
    efs.put_backup_policy(FileSystemId=fs, BackupPolicy={"Status": "DISABLED"})
    efs.create_mount_target(FileSystemId=fs, SubnetId=a, SecurityGroups=[sg])
    efs.create_access_point(FileSystemId=fs, RootDirectory={"Path": "/app"}, PosixUser={"Uid": 1000, "Gid": 1000},
                            Tags=tags("w2-efs-ap"))

    # ELBv2: an internal ALB across both subnets, a listener forwarding to a target group and a path rule
    elb = c("elbv2")
    tg = elb.create_target_group(Name="w2-tg", Protocol="HTTP", Port=80, VpcId=vpc, TargetType="instance",
                                 HealthCheckPath="/", Tags=tags("w2-tg"))["TargetGroups"][0]["TargetGroupArn"]
    lb = elb.create_load_balancer(Name="w2-alb", Type="application", Scheme="internal", Subnets=[a, b],
                                  SecurityGroups=[sg], Tags=tags("w2-alb"))["LoadBalancers"][0]
    # Floci binds each listener port inside its container, so keep clear of ports other scenarios use
    listener = elb.create_listener(LoadBalancerArn=lb["LoadBalancerArn"], Protocol="HTTP", Port=18091,
                                   DefaultActions=[{"Type": "forward", "TargetGroupArn": tg}],
                                   Tags=tags("w2-listener"))["Listeners"][0]["ListenerArn"]
    elb.create_rule(ListenerArn=listener, Priority=10,
                    Conditions=[{"Field": "path-pattern", "Values": ["/api/*"]}],
                    Actions=[{"Type": "forward", "TargetGroupArn": tg}], Tags=tags("w2-rule"))

    # Auto Scaling: a group over both subnets behind the target group, kept at zero so it launches nothing
    asg = c("autoscaling")
    asg.create_auto_scaling_group(AutoScalingGroupName="w2-asg", LaunchTemplate={"LaunchTemplateId": lt, "Version": "$Latest"},
                                  MinSize=0, MaxSize=2, DesiredCapacity=0, VPCZoneIdentifier=f"{a},{b}",
                                  TargetGroupARNs=[tg], HealthCheckType="ELB", HealthCheckGracePeriod=60,
                                  Tags=[{"Key": "Name", "Value": "w2-asg", "PropagateAtLaunch": True}])
    asg.put_scaling_policy(AutoScalingGroupName="w2-asg", PolicyName="w2-cpu50", PolicyType="TargetTrackingScaling",
                           TargetTrackingConfiguration={"PredefinedMetricSpecification": {
                               "PredefinedMetricType": "ASGAverageCPUUtilization"}, "TargetValue": 50.0})

    # Route 53: a private zone for the VPC with an A record and an alias to the load balancer
    r53 = c("route53")
    zone = r53.create_hosted_zone(Name="w2.internal", CallerReference="w2-zone", VPC={"VPCRegion": region, "VPCId": vpc},
                                  HostedZoneConfig={"Comment": "w2 private zone", "PrivateZone": True})["HostedZone"]["Id"]
    r53.change_resource_record_sets(HostedZoneId=zone, ChangeBatch={"Changes": [
        {"Action": "UPSERT", "ResourceRecordSet": {"Name": "db.w2.internal", "Type": "A", "TTL": 60,
                                                   "ResourceRecords": [{"Value": "10.91.1.20"}]}},
        {"Action": "UPSERT", "ResourceRecordSet": {"Name": "app.w2.internal", "Type": "A", "AliasTarget": {
            "HostedZoneId": lb["CanonicalHostedZoneId"], "DNSName": lb["DNSName"], "EvaluateTargetHealth": False}}}]})

