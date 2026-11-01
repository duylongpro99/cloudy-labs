# Wave 3: edge kinds (CloudFront, API Gateway, Global Accelerator, ACM, WAF, Route 53 health checks)

## Outcome

I added seven kinds: six in new registry files and one, the Route 53 health check, appended to `route53.yaml` as the brief allows. They all load.

- **Builder ops.** All 22 ops ran through `prepare` and the aws CLI on live Floci with exit 0. After each one, a fresh collect showed its result: a create's node appeared, a change altered a prop or an edge, and a delete removed the node. The probe ops were `pb-edge-ct-*`. The CloudFront update and delete were sent with the ETag that `get-distribution-config` returns. The WAF update and delete were sent with the LockToken from `get-web-acl`.
- **Scenario.** `make_edge` below ran on live Floci with `pb-edge-w3` names. A collect over it gave no warnings, and every expected edge resolved: origin to s3-bucket and to load-balancer, uses-certificate from the distribution and from an HTTPS listener, invokes from the REST API, the HTTP API and Lambda@Edge, web-acl-for to the load balancer, and uses-health-check from a failover record.
- **Coverage.** No gap reason names my services any more (details below).
- **Cleanup.** Every `pb-edge-` resource is deleted. A second cleanup pass found nothing.

Files:
- `server/src/cloudy_labs/registry/cloudfront.yaml` (new, 76 lines)
- `server/src/cloudy_labs/registry/apigateway.yaml` (new, 62 lines)
- `server/src/cloudy_labs/registry/apigatewayv2.yaml` (new, 59 lines)
- `server/src/cloudy_labs/registry/globalaccelerator.yaml` (new, 61 lines)
- `server/src/cloudy_labs/registry/acm.yaml` (new, 65 lines)
- `server/src/cloudy_labs/registry/wafv2.yaml` (new, 80 lines)
- `server/src/cloudy_labs/registry/route53.yaml` (appended the `route53-health-check` kind; the two existing kinds are unchanged)
- `server/tests/test_registry_edge.py` (new, 42 tests)

## Kinds added

| kind | service, scope | parent | edges (all on the new kind) | ops | contract | view order |
|---|---|---|---|---|---|---|
| `cloudfront-distribution` | cloudfront, global | global | `origin` to s3-bucket (global, regional and both website spellings), load-balancer (DNSName, `dualstack.`), apigateway-rest-api and apigateway-http-api (`<id>.execute-api.<region>.amazonaws.com`); `uses-certificate` to acm-certificate; `invokes` to lambda-version/lambda-function (Lambda@Edge) | create-distribution, update-distribution (attribute), delete-distribution | a bucket, then create (no `then`: update and delete need the ETag, which a contract step cannot pass) | 500 |
| `apigateway-rest-api` | apigateway | region | `invokes` to lambda-function / lambda-alias (the integration URI that wraps the ARN, read via GetResources embed=methods) | create-rest-api, create-deployment (attribute), delete-rest-api | create, then deploy to `dev`, then delete | 505 |
| `apigateway-http-api` | apigatewayv2 (ProtocolType HTTP only) | region | `invokes` to lambda-function / lambda-alias (GetIntegrations IntegrationUri) | create-http-api (quick create with Target), update-http-api, delete-http-api | create, update Description, delete | 506 |
| `global-accelerator` | globalaccelerator, global, control-plane-only | global | none | create-accelerator, update-accelerator, delete-accelerator | create, disable, delete | 510 |
| `acm-certificate` | acm | region | `uses-certificate` from listener (reverse; listener `Certificates[].CertificateArn`) | request-certificate, update-certificate-options, delete-certificate | create, transparency logging DISABLED, delete | 515 |
| `waf-web-acl` | wafv2, Scope REGIONAL, control-plane-only | region | `web-acl-for` to load-balancer (association; ListResourcesForWebACL) | create-web-acl, associate-web-acl (connect), update-web-acl, delete-web-acl | VPC 10.151, two subnets, an ALB; create, then associate | 520 |
| `route53-health-check` | route53, global | global | `uses-health-check` from record-set (reverse; HealthCheckId); `calculated-from` to child checks; `follows-alarm` to cloudwatch-alarm (AlarmName) | create-health-check, update-health-check, delete-health-check | create, update the path, delete | 525 |

Notes:
- **Edge kinds.** New edge kinds: `origin`, `uses-certificate`, `web-acl-for`, `uses-health-check`, `calculated-from` and `follows-alarm`, all `reference` except `web-acl-for` (`association`). `invokes` reuses the existing kind and style.
- **Edges and older kinds.** No existing kind got an edge, parent or scope pointing at a new kind.
- **View actions.** The view actions are kept to specific nouns (RestApi, Deployment, Api, Route, Distribution, Accelerator, Certificate, WebACL, HealthCheck). Generic words such as "Resource" or "Stage" would enter the coverage dictionary as terms for prose.
- **Icons.** All icons are real files under `aws-icon-pkg`:
  - CloudFront Download-Distribution (Res 48)
  - Arch API Gateway
  - API Gateway Endpoint (Res 48)
  - Arch Global Accelerator
  - Arch Certificate Manager
  - Arch WAF
  - Route 53 Readiness-Checks (Res 48)
- **Secrets.**
  - ACM reads metadata only, through DescribeCertificate. GetCertificate and ExportCertificate are never called, and a test enforces this.
  - The WAF LockToken and the CloudFront ETag-guarded config hold no secret. The LockToken is never a prop.
  - `etag` is shown on the distribution so the chat can fill IfMatch. It is a version tag, not a credential.
- **WAF scope.** Only REGIONAL web ACLs are listed. CLOUDFRONT-scope ACLs need the us-east-1 endpoint. Listing them in a lab in another region would fail on AWS, and that failure would take down the whole wafv2 service in the collector. So `create-web-acl` offers Scope REGIONAL only.
- **ACM key types.** The ACM list passes `Includes.keyTypes` with every key type, so EC certificates show up on AWS too. Floci accepts the parameter.
- **CloudFront actions.** CloudFront `create-invalidation` is left out to keep to one modify op. It is supported by Floci if a lab needs it later.

## APIs probed and Floci 2.3.0 quirks (all verified live)

- **CloudFront.**
  - A distribution is `Deployed` at once.
  - IfMatch is enforced on Update/Delete (InvalidIfMatchVersion), and an enabled distribution cannot be deleted (DistributionNotDisabled).
  - ListDistributions omits DefaultCacheBehavior and WebACLId, so the kind reads GetDistributionConfig.
  - **WebACLId is silently dropped** on create and update.
  - Requests are proxied to the origins without caching.
- **REST API.**
  - CreateDeployment works on an API with no methods. Real AWS refuses that, but the contract never relies on it.
  - GetResources with embed=methods returns the integration URIs.
- **HTTP API.**
  - Quick create (Target) makes the AWS_PROXY integration, the `$default` route and the `$default` stage.
  - CreateStage, GetStages, GetIntegration, UpdateIntegration and DeleteIntegration are missing. GetStages answers live anyway, but it is not listed, so the kind does not call it.
- **Global Accelerator.**
  - Fake IPs and DNS name.
  - An endpoint group accepts a nonexistent endpoint and reports it HEALTHY.
  - Delete is refused while listeners exist or the accelerator is enabled.
- **ACM.**
  - A requested certificate is ISSUED at once, with issuer `CN=Floci Local CA`.
  - InUseBy stays empty when an HTTPS ALB listener uses the certificate.
  - The listener's `Certificates` does carry the ARN, which the edge uses.
- **WAFv2.**
  - UpdateWebACL needs the current LockToken.
  - AssociateWebACL accepts nonexistent ARNs.
  - ListResourcesForWebACL ignores ResourceType.
  - Traffic is not inspected.
- **Route 53 health checks.**
  - GetHealthCheckStatus always reports `Success: HTTP Status Code 200, OK`, even for a name that does not resolve.
  - UpdateHealthCheck replaces the whole config with the fields sent; the others are lost.

## Caveats

- `cloudfront-no-edge-cache` (prop status)
- `cloudfront-web-acl-dropped` (prop webAcl)
- `apigateway-no-throttling` (prop stages)
- `apigatewayv2-no-create-stage`
- `globalaccelerator-config-only` (prop ips) and `floci: control-plane-only`
- `acm-issued-at-once` (prop status)
- `waf-no-inspection` (prop rules)
- `waf-accepts-unknown-resources` (prop resources) and `floci: control-plane-only`
- `route53-health-check-always-healthy` (prop status)
- `route53-health-check-update-replaces` (prop target)

## Missing APIs (for catalog-overrides.yaml)

- apigatewayv2: CreateStage, GetStages, GetIntegration, UpdateIntegration, DeleteIntegration
- apigateway: FlushStageCache (lab-100 and lab-92 cache labs)
- cloudfront: ListDistributionsByWebACLId

## Changes needed in files I do not own

1. **Recordings.**
   - The wave-2 replay now fails for route53 with `route53.list_health_checks was not recorded`. Because the whole service fails, hosted zones and records also vanish from that replay. The wave-2 recording, or its replay kinds, needs ListHealthChecks with an empty answer, as every other wave-3 service does.
   - The wave-3 recording should call `make_edge` below.
2. **Builder sanitizer.** `sanitize.py` refuses `*` in name fields, so `request-certificate` cannot ask for a wildcard `*.example.com` DomainName. That is a common real case. Allowing a leading `*.` for ACM `DomainName` and `SubjectAlternativeNames` would fix it.
3. **ImportCertificate (lab-15).** Floci supports it, but the builder would need sample certificate/key blobs, and blob samples are zip-only today. It needs a sample-PEM mechanism. The key would be a throwaway test key, never a real one.
4. **Hooks I could not express in JMESPath:**
   - A WAF association to an API Gateway stage. The ARN is `arn:aws:apigateway:<region>::/restapis/<id>/stages/<stage>` and would need a substring or split match on apigateway-rest-api.
   - Global Accelerator endpoint groups to load-balancer. This needs a per-listener ListEndpointGroups enrich.
5. **Registry export and web copy.** Both are regenerated by the controller; the new edge kinds are listed above.

## Coverage (labctl coverage --catalog)

- **Before:** 23 labs had a gap reason naming my services:
  - "no kind of cloudfront": 11
  - "no kind of apigateway": 10
  - "no kind of globalaccelerator": 2
  - "no kind of acm": 1
  - "no kind of wafv2": 1
  - "no kind for health check (route53)": 1 (lab-53)
  - "no kind for rest api (apigateway)": 1 (lab-118)

  Lab-060 and lab-118 each appear under two of these reasons.
- **After:** none. No lab is `gap` or `blocked` for these services, and with every wave-3 file loaded the whole catalog has `gap: 0`.
- **WAF rule group.** "rule group (network-firewall, waf, waf-regional, wafv2)" is reported only in the network-firewall labs 082/083 and was left to that group. It is also gone now.

## Tests

- `uv run pytest -q tests/test_registry_edge.py`: 42 passed. They cover:
  - band, icons and unique orders;
  - global scope and parent;
  - APIs present in floci-ops;
  - create/delete ops and string contract params;
  - no certificate body, key or LockToken in props;
  - the JMESPath of the REST integration, S3/ALB origin, HTTPS listener, failover record and WAF rules edges and props.
- Full suite: 768 passed, 8 failed.
  - Two failures are the expected export diffs: `test_registry_endpoint_matches_the_golden_and_the_web_copy` and `test_the_committed_matrix_is_what_the_generator_writes`.
  - Six are the wave-1 and wave-2 replay tests. They fail because the wave-3 services have no recorded answers. Wave-1 fails on rds `describe_event_subscriptions`, which is another group's kind. Wave-2 fails on every new service, including mine and route53 `list_health_checks`.
- `cognito-identity-pool set-identity-pool-roles` (another group's file) currently breaks `all_ops()` with `'MapShape' object has no attribute 'members'`. My op runs used a registry without that kind.

## Ready-to-paste scenario

Ran once on live Floci with `w3-edge` renamed to `pb-edge-w3` and 10.153 renamed to 10.154. It creates without error, and all of it was deleted afterwards.

```python
import io, json, sys, zipfile


def make_edge(c):
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
```

Status: DONE_WITH_CONCERNS
Summary: I added seven edge kinds (CloudFront distribution, REST API, HTTP API, Global Accelerator, ACM certificate, regional WAF web ACL, Route 53 health check) with 22 ops that work on live Floci, contracts, caveats, tests and a scenario. No coverage gap names these services any more.
Concerns/Blockers: My route53 health-check kind makes the wave-2 replay fail until `list_health_checks` is recorded. The CloudFront contract cannot exercise update or delete, because they need the ETag and a contract step cannot pass it. Wildcard ACM domains are refused by the sanitizer.
