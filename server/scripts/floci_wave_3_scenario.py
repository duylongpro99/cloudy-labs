"""The third-wave scenario: one of every edge, messaging, delivery, data movement and governance
kind, linked to each other where AWS links them. `record-floci-fixtures.py build-wave-3` runs it on
an empty Floci.

Every function takes `c`, a function from service name to a boto3 client pointed at Floci. Values
are dummies; no password or secret value is created, and the collector reads only metadata.
EKS, ECR and ElastiCache start real containers on Floci; `labctl down` removes them.
"""

from __future__ import annotations

import io
import json
import time
import zipfile


def build_edge(c):
    """One of every edge kind on an empty Floci, linked as AWS links them: a CloudFront distribution in
    front of an S3 bucket and an ALB with an ACM certificate and a Lambda@Edge version, a REST API and an
    HTTP API calling a Lambda function, a Global Accelerator on the ALB, a WAF web ACL on the ALB, and a
    Route 53 health check named by a failover record."""
    region = "ap-southeast-2"
    s3, ec2, elb, lam, iam = c("s3"), c("ec2"), c("elbv2"), c("lambda"), c("iam")
    # Origin bucket.
    bucket = "w3-edge-origin"
    s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})
    # An ALB with an HTTPS listener using an ACM certificate.
    vpc = ec2.create_vpc(CidrBlock="10.153.0.0/16")["Vpc"]["VpcId"]
    ec2.create_tags(Resources=[vpc], Tags=[{"Key": "Name", "Value": "w3-edge-vpc"}])
    subnets = [ec2.create_subnet(VpcId=vpc, CidrBlock=f"10.153.{i}.0/24", AvailabilityZone=f"{region}{az}")["Subnet"]["SubnetId"]
               for i, az in ((1, "a"), (2, "b"))]
    lb = elb.create_load_balancer(Name="w3-edge-alb", Subnets=subnets, Type="application")["LoadBalancers"][0]
    cert = c("acm").request_certificate(DomainName="w3-edge.example.com", ValidationMethod="DNS")["CertificateArn"]
    elb.create_listener(LoadBalancerArn=lb["LoadBalancerArn"], Protocol="HTTPS", Port=443, Certificates=[{"CertificateArn": cert}],
                        DefaultActions=[{"Type": "fixed-response", "FixedResponseConfig": {"StatusCode": "200"}}])
    # A Lambda function (and a published version for Lambda@Edge).
    role = iam.create_role(RoleName="w3-edge-fn-role", AssumeRolePolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                                                "Principal": {"Service": ["lambda.amazonaws.com", "edgelambda.amazonaws.com"]}}]}))["Role"]["Arn"]
    code = io.BytesIO()
    with zipfile.ZipFile(code, "w") as z:
        z.writestr("index.py", "def handler(event, context):\n    return {'statusCode': 200, 'body': 'ok'}\n")
    fn = lam.create_function(FunctionName="w3-edge-fn", Runtime="python3.12", Role=role, Handler="index.handler",
                             Code={"ZipFile": code.getvalue()})["FunctionArn"]
    version = lam.publish_version(FunctionName="w3-edge-fn")["FunctionArn"]
    # CloudFront: the bucket and the ALB as origins, the certificate, Lambda@Edge on viewer requests.
    c("cloudfront").create_distribution(DistributionConfig={
        "CallerReference": "w3-edge-cf", "Comment": "w3-edge-cf", "Enabled": True,
        "Aliases": {"Quantity": 1, "Items": ["w3-edge.example.com"]},
        "Origins": {"Quantity": 2, "Items": [
            {"Id": "s3", "DomainName": f"{bucket}.s3.{region}.amazonaws.com", "S3OriginConfig": {"OriginAccessIdentity": ""}},
            {"Id": "alb", "DomainName": lb["DNSName"], "CustomOriginConfig": {"HTTPPort": 80, "HTTPSPort": 443, "OriginProtocolPolicy": "https-only"}}]},
        "DefaultCacheBehavior": {"TargetOriginId": "s3", "ViewerProtocolPolicy": "redirect-to-https",
                                 "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
                                 "LambdaFunctionAssociations": {"Quantity": 1, "Items": [{"LambdaFunctionARN": version, "EventType": "viewer-request"}]}},
        "ViewerCertificate": {"ACMCertificateArn": cert, "SSLSupportMethod": "sni-only", "MinimumProtocolVersion": "TLSv1.2_2021"}})
    # REST API: GET /items with a Lambda proxy integration, deployed to prod.
    ag = c("apigateway")
    api = ag.create_rest_api(name="w3-edge-rest", endpointConfiguration={"types": ["REGIONAL"]})
    items = ag.create_resource(restApiId=api["id"], parentId=api["rootResourceId"], pathPart="items")["id"]
    ag.put_method(restApiId=api["id"], resourceId=items, httpMethod="GET", authorizationType="NONE")
    ag.put_integration(restApiId=api["id"], resourceId=items, httpMethod="GET", type="AWS_PROXY", integrationHttpMethod="POST",
                       uri=f"arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{fn}/invocations")
    ag.create_deployment(restApiId=api["id"], stageName="prod")
    # HTTP API, quick-created on the function.
    c("apigatewayv2").create_api(Name="w3-edge-http", ProtocolType="HTTP", Target=fn)
    # Global Accelerator: a TCP 80 listener sending traffic to the ALB.
    ga = c("globalaccelerator")
    acc = ga.create_accelerator(Name="w3-edge-ga", IpAddressType="IPV4", Enabled=True)["Accelerator"]["AcceleratorArn"]
    listener = ga.create_listener(AcceleratorArn=acc, Protocol="TCP", PortRanges=[{"FromPort": 80, "ToPort": 80}])["Listener"]["ListenerArn"]
    ga.create_endpoint_group(ListenerArn=listener, EndpointGroupRegion=region,
                             EndpointConfigurations=[{"EndpointId": lb["LoadBalancerArn"], "Weight": 100}])
    # WAF: a rate-based rule, associated with the ALB.
    waf = c("wafv2")
    acl = waf.create_web_acl(Name="w3-edge-acl", Scope="REGIONAL", DefaultAction={"Allow": {}},
                             VisibilityConfig={"SampledRequestsEnabled": True, "CloudWatchMetricsEnabled": True, "MetricName": "w3-edge-acl"},
                             Rules=[{"Name": "rate-limit", "Priority": 0, "Action": {"Block": {}},
                                     "Statement": {"RateBasedStatement": {"Limit": 100, "AggregateKeyType": "IP"}},
                                     "VisibilityConfig": {"SampledRequestsEnabled": True, "CloudWatchMetricsEnabled": True, "MetricName": "rate-limit"}}])
    waf.associate_web_acl(WebACLArn=acl["Summary"]["ARN"], ResourceArn=lb["LoadBalancerArn"])
    # Route 53: a health check on the ALB, named by the PRIMARY failover record.
    r53 = c("route53")
    hc = r53.create_health_check(CallerReference="w3-edge-hc", HealthCheckConfig={
        "Type": "HTTP", "FullyQualifiedDomainName": lb["DNSName"], "Port": 80, "ResourcePath": "/", "RequestInterval": 30, "FailureThreshold": 3})["HealthCheck"]["Id"]
    r53.change_tags_for_resource(ResourceType="healthcheck", ResourceId=hc, AddTags=[{"Key": "Name", "Value": "w3-edge-hc"}])
    zone = r53.create_hosted_zone(Name="w3-edge.example.com", CallerReference="w3-edge-zone")["HostedZone"]["Id"]
    r53.change_resource_record_sets(HostedZoneId=zone, ChangeBatch={"Changes": [
        {"Action": "CREATE", "ResourceRecordSet": {"Name": "app.w3-edge.example.com", "Type": "A", "SetIdentifier": "primary", "Failover": "PRIMARY",
                                                   "TTL": 60, "HealthCheckId": hc, "ResourceRecords": [{"Value": "10.153.1.10"}]}},
        {"Action": "CREATE", "ResourceRecordSet": {"Name": "app.w3-edge.example.com", "Type": "A", "SetIdentifier": "secondary", "Failover": "SECONDARY",
                                                   "TTL": 60, "ResourceRecords": [{"Value": "10.153.2.10"}]}}]})

def build_messaging(c):
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

def build_delivery(c):
    """One of every delivery kind: an ECR repository, an ECS cluster, an EKS cluster (Floci starts a
    k3s container for it), a Beanstalk application with an environment, a CodeBuild project, a
    CodeDeploy application, a pipeline S3 source -> CodeBuild -> Beanstalk, and a CodeArtifact domain
    holding a repository with an upstream."""
    p = "w3-"
    region = c("s3").meta.region_name
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {
        "Service": ["codebuild.amazonaws.com", "codepipeline.amazonaws.com", "eks.amazonaws.com"]}}]}
    role = c("iam").create_role(RoleName=f"{p}delivery-role", AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
    bucket = f"{p}delivery-artifacts"
    c("s3").create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})

    c("ecr").create_repository(repositoryName=f"{p}delivery-app", imageScanningConfiguration={"scanOnPush": True})
    c("ecs").create_cluster(clusterName=f"{p}delivery", settings=[{"name": "containerInsights", "value": "enabled"}])
    c("eks").create_cluster(name=f"{p}delivery", roleArn=role, resourcesVpcConfig={"endpointPublicAccess": True})

    eb = c("elasticbeanstalk")
    eb.create_application(ApplicationName=f"{p}delivery-web", Description="dummy web app")
    eb.create_environment(ApplicationName=f"{p}delivery-web", EnvironmentName=f"{p}delivery-web-dev",
                          SolutionStackName="64bit Amazon Linux 2023 v4.3.0 running Docker",
                          OptionSettings=[{"Namespace": "aws:elasticbeanstalk:command", "OptionName": "DeploymentPolicy",
                                           "Value": "Rolling"}])

    c("codebuild").create_project(
        name=f"{p}delivery-build", serviceRole=role, source={"type": "CODEPIPELINE"},
        artifacts={"type": "CODEPIPELINE"},
        environment={"type": "LINUX_CONTAINER", "image": "aws/codebuild/standard:7.0", "computeType": "BUILD_GENERAL1_SMALL",
                     "environmentVariables": [{"name": "STAGE", "value": "w3-dummy-env", "type": "PLAINTEXT"}]})
    c("codedeploy").create_application(applicationName=f"{p}delivery-deploy", computePlatform="Server")

    c("codepipeline").create_pipeline(pipeline={
        "name": f"{p}delivery-pipeline", "roleArn": role, "artifactStore": {"type": "S3", "location": bucket},
        "stages": [
            {"name": "Source", "actions": [{"name": "Source", "actionTypeId": {"category": "Source", "owner": "AWS", "provider": "S3", "version": "1"},
                                            "configuration": {"S3Bucket": bucket, "S3ObjectKey": "source.zip", "PollForSourceChanges": "false"},
                                            "outputArtifacts": [{"name": "src"}]}]},
            {"name": "Build", "actions": [{"name": "Build", "actionTypeId": {"category": "Build", "owner": "AWS", "provider": "CodeBuild", "version": "1"},
                                           "configuration": {"ProjectName": f"{p}delivery-build"},
                                           "inputArtifacts": [{"name": "src"}], "outputArtifacts": [{"name": "out"}]}]},
            {"name": "Deploy", "actions": [{"name": "Deploy", "actionTypeId": {"category": "Deploy", "owner": "AWS", "provider": "ElasticBeanstalk", "version": "1"},
                                            "configuration": {"ApplicationName": f"{p}delivery-web", "EnvironmentName": f"{p}delivery-web-dev"},
                                            "inputArtifacts": [{"name": "out"}]}]}]})

    ca = c("codeartifact")
    ca.create_domain(domain=f"{p}delivery")
    ca.create_repository(domain=f"{p}delivery", repository=f"{p}delivery-npm-store")
    ca.associate_external_connection(domain=f"{p}delivery", repository=f"{p}delivery-npm-store", externalConnection="public:npmjs")
    ca.create_repository(domain=f"{p}delivery", repository=f"{p}delivery-libs", upstreams=[{"repositoryName": f"{p}delivery-npm-store"}])


def build_datamove(c):
    """DMS, DataSync, ElastiCache, Athena, Glue, Transfer Family and an RDS event subscription,
    linked as AWS links them: DMS and ElastiCache in a VPC, a DMS source endpoint at an RDS
    instance, an S3 target endpoint and DataSync locations on one bucket, a crawler into a Glue
    database, a VPC-hosted SFTP server, and an event subscription watching the RDS instance."""
    region = "ap-southeast-2"
    ec2, iam, s3, sns, rds = c("ec2"), c("iam"), c("s3"), c("sns"), c("rds")

    def tags(name, kind):
        return [{"ResourceType": kind, "Tags": [{"Key": "Name", "Value": name}]}]

    vpc = ec2.create_vpc(CidrBlock="10.72.0.0/16", TagSpecifications=tags("w3-dm-vpc", "vpc"))["Vpc"]["VpcId"]
    a = ec2.create_subnet(VpcId=vpc, CidrBlock="10.72.1.0/24", AvailabilityZone=f"{region}a",
                          TagSpecifications=tags("w3-dm-a", "subnet"))["Subnet"]["SubnetId"]
    b = ec2.create_subnet(VpcId=vpc, CidrBlock="10.72.2.0/24", AvailabilityZone=f"{region}b",
                          TagSpecifications=tags("w3-dm-b", "subnet"))["Subnet"]["SubnetId"]
    sg = ec2.create_security_group(GroupName="w3-dm-sg", Description="w3 data movement", VpcId=vpc)["GroupId"]

    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {"Service": [
        "dms.amazonaws.com", "datasync.amazonaws.com", "glue.amazonaws.com", "transfer.amazonaws.com"]}}]}
    role = iam.create_role(RoleName="w3-dm-role", AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
    s3.create_bucket(Bucket="w3-dm-bucket", CreateBucketConfiguration={"LocationConstraint": region})
    topic = sns.create_topic(Name="w3-dm-events")["TopicArn"]

    # The DMS source: a PostgreSQL instance whose master password RDS keeps itself (no value here).
    rds.create_db_instance(DBInstanceIdentifier="w3-dm-db", Engine="postgres", DBInstanceClass="db.t3.micro",
                           MasterUsername="w3admin", ManageMasterUserPassword=True, AllocatedStorage=20)
    for _ in range(60):
        db = rds.describe_db_instances(DBInstanceIdentifier="w3-dm-db")["DBInstances"][0]
        if db.get("Endpoint"):
            break
        time.sleep(1)
    else:
        raise RuntimeError("w3-dm-db has no endpoint after 60 s")

    dms = c("dms")
    dms.create_replication_subnet_group(ReplicationSubnetGroupIdentifier="w3-dm-rsg",
                                        ReplicationSubnetGroupDescription="w3 data movement", SubnetIds=[a, b])
    ri = dms.create_replication_instance(ReplicationInstanceIdentifier="w3-dm-ri", ReplicationInstanceClass="dms.t3.micro",
                                         AllocatedStorage=20, ReplicationSubnetGroupIdentifier="w3-dm-rsg",
                                         VpcSecurityGroupIds=[sg])["ReplicationInstance"]["ReplicationInstanceArn"]
    src = dms.create_endpoint(EndpointIdentifier="w3-dm-src", EndpointType="source", EngineName="postgres",
                              ServerName=db["Endpoint"]["Address"], Port=db["Endpoint"]["Port"],
                              DatabaseName="postgres", Username="w3admin")["Endpoint"]["EndpointArn"]
    tgt = dms.create_endpoint(EndpointIdentifier="w3-dm-tgt", EndpointType="target", EngineName="s3",
                              S3Settings={"BucketName": "w3-dm-bucket", "BucketFolder": "dms",
                                          "ServiceAccessRoleArn": role})["Endpoint"]["EndpointArn"]
    mappings = {"rules": [{"rule-type": "selection", "rule-id": "1", "rule-name": "all",
                           "object-locator": {"schema-name": "%", "table-name": "%"}, "rule-action": "include"}]}
    dms.create_replication_task(ReplicationTaskIdentifier="w3-dm-task", ReplicationInstanceArn=ri, SourceEndpointArn=src,
                                TargetEndpointArn=tgt, MigrationType="full-load", TableMappings=json.dumps(mappings))

    ds = c("datasync")
    bucket_arn = "arn:aws:s3:::w3-dm-bucket"
    loc_in = ds.create_location_s3(S3BucketArn=bucket_arn, Subdirectory="/in",
                                   S3Config={"BucketAccessRoleArn": role})["LocationArn"]
    loc_out = ds.create_location_s3(S3BucketArn=bucket_arn, Subdirectory="/archive", S3StorageClass="STANDARD_IA",
                                    S3Config={"BucketAccessRoleArn": role})["LocationArn"]
    ds.create_task(Name="w3-dm-sync", SourceLocationArn=loc_in, DestinationLocationArn=loc_out,
                   Schedule={"ScheduleExpression": "rate(1 hour)"})

    # Floci starts a Valkey and a Memcached container for these.
    ec = c("elasticache")
    ec.create_cache_subnet_group(CacheSubnetGroupName="w3-dm-csg", CacheSubnetGroupDescription="w3 data movement",
                                 SubnetIds=[a, b])
    ec.create_replication_group(ReplicationGroupId="w3-dm-redis", ReplicationGroupDescription="w3 data movement",
                                Engine="valkey", CacheNodeType="cache.t3.micro", NumCacheClusters=2,
                                AutomaticFailoverEnabled=True, CacheSubnetGroupName="w3-dm-csg", SecurityGroupIds=[sg])
    ec.create_cache_cluster(CacheClusterId="w3-dm-memcached", Engine="memcached", CacheNodeType="cache.t3.micro",
                            NumCacheNodes=1, CacheSubnetGroupName="w3-dm-csg", SecurityGroupIds=[sg])

    c("athena").create_work_group(Name="w3-dm-wg", Description="w3 data movement", Configuration={
        "ResultConfiguration": {"OutputLocation": "s3://w3-dm-bucket/athena/"}, "EnforceWorkGroupConfiguration": True})

    glue = c("glue")
    glue.create_database(DatabaseInput={"Name": "w3_dm_db", "Description": "w3 data movement"})
    glue.create_crawler(Name="w3-dm-crawler", Role=role, DatabaseName="w3_dm_db",
                        Targets={"S3Targets": [{"Path": "s3://w3-dm-bucket/in/"}]}, Schedule="cron(0 2 * * ? *)")

    c("transfer").create_server(Protocols=["SFTP"], EndpointType="VPC", IdentityProviderType="SERVICE_MANAGED", Domain="S3",
                                EndpointDetails={"VpcId": vpc, "SubnetIds": [a], "SecurityGroupIds": [sg]},
                                LoggingRole=role, Tags=[{"Key": "Name", "Value": "w3-dm-sftp"}])

    # SourceIds given on create are dropped by Floci 2.3.0; adding the source afterwards keeps it.
    rds.create_event_subscription(SubscriptionName="w3-dm-db-events", SnsTopicArn=topic, SourceType="db-instance",
                                  EventCategories=["availability", "failover"])
    rds.add_source_identifier_to_subscription(SubscriptionName="w3-dm-db-events", SourceIdentifier="w3-dm-db")


def build_governance(c, prefix="w3-", sticky=True):
    """One of every governance kind, linked as AWS links them. c: service name -> boto3 client on Floci.

    sticky=False skips Inspector and Security Hub, which Floci 2.3.0 cannot disable once enabled."""
    region = c("sts").meta.region_name
    under = prefix.replace("-", "_")
    s3, iam = c("s3"), c("iam")
    bucket = f"{prefix}governance-logs"
    s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})
    def trust(principal):
        action = "sts:AssumeRole" if "Service" in principal else "sts:AssumeRoleWithWebIdentity"
        return json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": principal, "Action": action}]})

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
