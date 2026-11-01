# Wave 3: data movement kinds (DMS, DataSync, ElastiCache, Athena, Glue, Transfer Family, RDS event subscriptions)

## Outcome

I added twelve kinds. Every create op went through `prepare()` and the aws CLI against live Floci 2.3.0, and every contract passed with about 1 s per step. A live collect of the scenario below produced every expected parent and edge and no warnings. All 121 catalog gaps for these services are now closed: dms 11, elasticache 7, athena 6, datasync 6, transfer 3, rds 15. The only full-suite failure caused by these files is the wave-1 replay, because the new rds kind lists `describe_event_subscriptions`, which the wave-1 recording does not hold. The recording fix is described under "Changes needed in files I do not own".

Event subscriptions: of dms, docdb, neptune and redshift, Floci 2.3.0 has event subscriptions for **none**. Only rds has `CreateEventSubscription`, `DescribeEventSubscriptions` and the related calls.

## Kinds added (view.order 650-699; used 650, 651, 652, 655, 656, 660, 661, 665, 670, 671, 675, 680)

| Kind | Order | Parent | Edges | Ops | Contract | Caveats | Floci |
|---|---|---|---|---|---|---|---|
| `dms-replication-instance` | 650 | vpc (`ReplicationSubnetGroup.VpcId`), else region | attached (reverse, from SG), subnet-group-member | create / modify (class) / delete-replication-instance | create, modify to dms.t3.small, delete | flag-only (multiAz), dms-no-private-ip | control-plane-only |
| `dms-endpoint` | 651 | region | endpoint-database to db-instance and to db-cluster, matched on `address:port`; uses-bucket to s3-bucket; execution-role | create / modify / delete-dms-endpoint | create a postgres endpoint, modify, delete | dms-endpoint-not-tested | control-plane-only |
| `dms-replication-task` | 652 | region | runs-on, copies-from, copies-to | create / start / stop / delete-replication-task | needs an instance and two endpoints; start, stop, delete | dms-task-moves-no-data | control-plane-only |
| `datasync-location` | 655 | region | execution-role | create-location-s3, update-location-s3, delete-datasync-location | needs a role and a bucket; update to STANDARD_IA, delete | none | control-plane-only |
| `datasync-task` | 656 | region | copies-from, copies-to | create / update (schedule) / delete-datasync-task | needs two buckets and two locations; update, delete | datasync-task-never-runs | control-plane-only |
| `elasticache-replication-group` | 660 | vpc (from the cache subnet group of its first member) | attached (reverse), subnet-group-member | create / modify (snapshot retention) / delete-replication-group | create valkey with 2 nodes, modify, delete (max 10 s) | elasticache-endpoint-not-published, elasticache-node-type-ignored, elasticache-no-security-groups, flag-only | supported (real Valkey container) |
| `elasticache-cache-cluster` | 661 | vpc | attached (reverse), subnet-group-member | create / delete-cache-cluster | create memcached, delete (max 10 s) | elasticache-endpoint-not-published | supported (real container) |
| `athena-workgroup` | 665 | region | none | create / update (state) / delete-work-group | create, disable, delete | athena-query-results-fail | supported |
| `glue-database` | 670 | region | none | create / delete-glue-database | create, delete | none | supported |
| `glue-crawler` | 671 | region | crawls-into, execution-role | create / update (schedule) / delete-crawler | needs a role and a database; update, delete | glue-crawler-finds-no-tables | control-plane-only |
| `transfer-server` | 675 | vpc (`EndpointDetails.VpcId`), else region | execution-role (LoggingRole), endpoint-subnet, attached (reverse SG) | create / stop / start / delete-transfer-server | create, stop, start, delete | transfer-endpoint-sg-dropped, transfer-no-file-endpoint | control-plane-only |
| `rds-event-subscription` (in `rds.yaml`) | 680 | region | watches to db-instance and db-cluster | create / modify (enabled) / add-source-identifier-to-subscription / delete-event-subscription | needs an SNS topic; modify, delete | rds-event-categories-dropped, rds-event-source-ids-dropped | control-plane-only |

These are the new edge kinds, all with reference style: runs-on, copies-from, copies-to, endpoint-database, uses-bucket and crawls-into. The edge kinds attached, subnet-group-member, execution-role, watches and endpoint-subnet already existed and were reused.

Design notes:
- **`dms-endpoint` matches on address and port.** Floci gives every RDS instance the same address (172.27.0.x) and a port of its own, so matching on the address alone would link an endpoint to every database. The match is `ServerName:Port` against `Endpoint.Address:Endpoint.Port`, and for a cluster against both the writer and the reader endpoint.
- **The replication group reads its subnet group and SGs from its first member cluster.** `DescribeReplicationGroups` does not return them. Member clusters are filtered out of `elasticache-cache-cluster` so that each one is drawn only once.
- **Workgroup and crawler ids follow the `<kind>:<region>:<name>` scheme.** The API returns no ARN for either. The Glue database id is the IAM ARN built from `CatalogId`. The `primary` workgroup is hidden.
- **`rds-event-subscription` edges point only at rds kinds, so `test_coverage.py` stays green.** That test pins a subset registry.

## Missing APIs (not in floci-ops-2.3.0.json, so no op was added)

- elasticache: `ModifyCacheCluster` (there is no modify op for a standalone cluster), `AddTagsToResource`.
- datasync: `StartTaskExecution`, `DescribeTaskExecution`, `ListTaskExecutions`, `CancelTaskExecution`. A task cannot be run.
- glue: `UpdateDatabase` (there is no modify op for a database).
- dms: `CreateEventSubscription` and the other event-subscription calls, plus `ModifyReplicationSubnetGroup`.
- docdb, neptune, redshift: no event-subscription APIs.

## Floci quirks found (verified live; each became a caveat)

- **DMS has no data plane.** A replication instance is a record with no private IP and no container. Multi-AZ is only a flag. `TestConnection` is never attempted. A task moves from starting to running to stopped but copies nothing.
- **DataSync tasks never execute.** No execution API exists.
- **ElastiCache runs real containers that the host cannot reach.** Floci starts a real Valkey or Memcached container per cluster and removes it on delete. It reports a localhost address and port (6379, 6380 and so on) that the lab stack does not publish. A new `CacheNodeType` passed to `ModifyReplicationGroup` is accepted and ignored. Member clusters report no security groups.
- **Athena queries fail at the results step.** Floci starts a DuckDB container (`floci-aws-duck`), but the query ends FAILED because the container cannot write results to the S3 output location (it cannot reach localhost.floci.io).
- **A Glue crawler finds nothing.** It reaches SUCCEEDED without reading its S3 paths, and no tables are written.
- **Transfer Family has no endpoint and drops the SG.** It drops `EndpointDetails.SecurityGroupIds` on a VPC server, and no SFTP, FTPS or FTP endpoint runs.
- **RDS event subscriptions drop their sources and categories.** `CreateEventSubscription` drops `SourceIds` and `EventCategories`. `AddSourceIdentifierToSubscription` does keep a source, which is why the scenario adds it afterwards.
- **The managed master secret is deleted with its DB.** With `ManageMasterUserPassword`, RDS creates a `rds!db-...` secret in Secrets Manager, and Floci deletes it together with the DB instance. The wave-3 recording will therefore include a secretsmanager secret for `w3-dm-db`, with its name only.

## Changes needed in files I do not own

1. **Wave-1 recording, which causes the only failures that come from these files.** `tests/test_collector_replay.py` fails three tests with `rds.describe_event_subscriptions was not recorded`. I confirmed that the wave-1 graph equals the golden graph, with no warnings, when `rds-event-subscription` is left out. To fix it, add `server/tests/fixtures/graph/floci-describe/rds/describe_event_subscriptions.json` containing `{"calls": [{"params": {}, "response": {"EventSubscriptionsList": []}}]}`, or re-record wave 1.
2. **A `notifies` edge from rds-event-subscription to sns-topic** (target `SnsTopicArn`). It could not go in rds.yaml, because the subset registry in `test_coverage.py` has no sns kinds. It should be added once that subset includes sns, or through a hook.
3. **A hook to link S3 URIs to their bucket.** DataSync S3 locations (`LocationUri`), the Athena `outputLocation` and crawler `s3Paths` are `s3://bucket/prefix/` URIs. A JMESPath edge cannot strip the prefix, so a hook (for example `common.s3_uri_bucket`) would let these kinds point at s3-bucket. The DMS S3 target already links through `S3Settings.BucketName`.
4. **Web icons** for the 12 new kinds, copied from the `view.source` paths. All of those sources exist under `aws-icon-pkg/`.
5. **Regenerated outputs:** the `registry.json` golden and web copy, the coverage matrix (`labctl coverage --matrix`), and catalog overrides for the missing APIs listed above.

## Tests

- `server/tests/test_registry_datamove.py` passes (51 tests). It checks that:
  - Each icon is real and its order falls inside the band, with no duplicate orders.
  - Every op API is one Floci has.
  - Every kind has create and delete ops, and its contract ends with a delete and uses only string params.
  - No prop reads a password, secret or key.
  - The rds kind points only at the older services' kinds.
  - Replication-group members are filtered out of the cache-cluster kind.
- `uv run pytest -q`: 768 passed, 8 failed.
  - The two expected failures: `test_registry_endpoint_matches_the_golden_and_the_web_copy` and `test_the_committed_matrix_is_what_the_generator_writes`.
  - Three wave-2 replay failures, caused by the new services from every wave-3 group (`no fake client for acm/athena/...`).
  - Three wave-1 replay failures, caused by my rds kind (item 1 above).
- All contracts were run live with `pb-datamove-ct-` names, and every builder op went through `prepare()` and the aws CLI. A live collect of the scenario showed no warnings.

## Coverage

| | blocked | gap | ready-with-caveats | ready |
|---|---|---|---|---|
| before (all groups' files absent) | 61 | 121 | 347 | 1 |
| after (all wave-3 files present) | 61 | 0 | 468 | 1 |

These gap reasons are gone: "no kind of dms" (11), "no kind of elasticache" (7), "no kind of athena" (6), "no kind of datasync" (6), "no kind of transfer" (3), "no kind for replication instance (dms)" (2), "no kind for replication group (elasticache)" (1) and "no kind for event subscription (dms, docdb, neptune, rds, redshift)" (1). Coverage reported no warnings.

## Probe cleanup

Everything named `pb-datamove-` or `pb_datamove_` has been deleted and the deletion verified:
- 4 DMS instances, 6 endpoints, 2 tasks and 2 subnet groups.
- 2 DataSync tasks, 6 locations and 1 agent.
- 2 replication groups, 2 cache clusters and 2 cache subnet groups. Their containers are gone.
- 2 workgroups, 2 crawlers and 3 Glue databases.
- 3 Transfer servers and 4 event subscriptions.
- 3 RDS instances, along with their 2 managed secrets.
- 3 SNS topics, 1 SQS queue, 5 buckets, 5 roles, and 2 VPCs with their subnets and SGs.

## Ready-to-paste scenario function

It uses `w3-dm-` names and CIDR 10.72.0.0/16. It ran once on an empty Floci under `pb-datamove-mk-` names and CIDR 10.73, and those resources were then deleted. It contains no password: the DB uses `ManageMasterUserPassword`.

```python
import json
import time


def make_datamove(c):
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
```

```text
Status: DONE_WITH_CONCERNS
Summary: Twelve data movement kinds (DMS, DataSync, ElastiCache, Athena, Glue, Transfer Family, RDS event subscriptions) were added and verified live with contracts. All 121 of these services' catalog gaps are closed, and every probe has been deleted.
Concerns/Blockers: The wave-1 replay fails (3 tests) until rds/describe_event_subscriptions.json is added to the wave-1 recording, as described above. Also outstanding: a notifies edge to sns-topic, an S3 URI-to-bucket hook, web icons, and regenerated golden and matrix files.
