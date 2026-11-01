"""Setup and checks for Lab 001. Resources are found by the names the lab asks for; the VPC by its
lab tag. Ids returned are the ones the scene uses: EC2 ids, and ARNs for RDS and Secrets Manager.

Floci 2.3.0 keeps StorageType as gp2 whatever is asked, so the gp3 check is shown, not graded.
A failover on Floci swaps the writer flag only; the check reads that flag.
"""

import ipaddress

from botocore.exceptions import ClientError

from cloudy_labs.checks import CheckContext, CheckResult

LAB = "lab-001"
LAB_TAG = [{"Name": "tag:lab", "Values": [LAB]}]
VPC_CIDR = "10.1.0.0/16"
PRIVATE_SUBNETS = [("lab-001-private-a", "10.1.11.0/24", "a"), ("lab-001-private-b", "10.1.12.0/24", "b")]
APP_SG = "lab-001-sg-app"
DB_SG = "lab-001-sg-database"
SUBNET_GROUP = "lab-001-dbsubnet-group"
RDS_ID = "lab-001-rds-mysql-standard"
CLUSTER_ID = "lab-001-aurora-cluster"
SECRET = "lab-001-db-credentials"
MYSQL_PORT = 3306
WORLD = {"0.0.0.0/0", "::/0"}


def _tags(resource_type: str, name: str) -> list[dict]:
    return [{"ResourceType": resource_type, "Tags": [{"Key": "Name", "Value": name}, {"Key": "lab", "Value": LAB}]}]


def setup_network(ctx: CheckContext) -> None:
    ec2 = ctx.client("ec2")
    vpc = ec2.create_vpc(CidrBlock=VPC_CIDR, TagSpecifications=_tags("vpc", "lab-001-vpc"))["Vpc"]["VpcId"]
    ec2.modify_vpc_attribute(VpcId=vpc, EnableDnsHostnames={"Value": True})
    region = ec2.meta.region_name
    for name, cidr, zone in PRIVATE_SUBNETS:
        ec2.create_subnet(VpcId=vpc, CidrBlock=cidr, AvailabilityZone=f"{region}{zone}",
                          TagSpecifications=_tags("subnet", name))
    ec2.create_security_group(GroupName=APP_SG, Description="Lab 001 application tier", VpcId=vpc,
                              TagSpecifications=_tags("security-group", APP_SG))


def _vpc(ctx: CheckContext) -> dict | None:
    vpcs = ctx.client("ec2").describe_vpcs(Filters=LAB_TAG)["Vpcs"]
    return vpcs[0] if vpcs else None


def _no_vpc() -> CheckResult:
    return CheckResult(False, "no VPC tagged lab=lab-001; run `labctl reset lab-001` to rebuild the network")


def _by_vpc(vpc_id: str, *more: dict) -> list[dict]:
    return [{"Name": "vpc-id", "Values": [vpc_id]}, *more]


def _sg(ctx: CheckContext, vpc_id: str, name: str) -> dict | None:
    groups = ctx.client("ec2").describe_security_groups(
        Filters=_by_vpc(vpc_id, {"Name": "group-name", "Values": [name]}))["SecurityGroups"]
    return groups[0] if groups else None


def _subnet_group(ctx: CheckContext) -> dict | None:
    try:
        return ctx.client("rds").describe_db_subnet_groups(DBSubnetGroupName=SUBNET_GROUP)["DBSubnetGroups"][0]
    except ClientError:
        return None


def _instance(ctx: CheckContext, identifier: str) -> dict | None:
    try:
        return ctx.client("rds").describe_db_instances(DBInstanceIdentifier=identifier)["DBInstances"][0]
    except ClientError:
        return None


def _cluster(ctx: CheckContext) -> dict | None:
    try:
        return ctx.client("rds").describe_db_clusters(DBClusterIdentifier=CLUSTER_ID)["DBClusters"][0]
    except ClientError:
        return None


def network_ready(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    subnets = ctx.client("ec2").describe_subnets(Filters=_by_vpc(vpc["VpcId"]))["Subnets"]
    app = _sg(ctx, vpc["VpcId"], APP_SG)
    azs = {s["AvailabilityZone"] for s in subnets}
    ids = [vpc["VpcId"], *sorted(s["SubnetId"] for s in subnets), *([app["GroupId"]] if app else [])]
    if len(azs) < 2 or app is None:
        return CheckResult(False, f"the lab network is incomplete ({len(subnets)} subnet(s) in {len(azs)} AZ, "
                                  f"app SG {'found' if app else 'missing'}); run `labctl reset lab-001`", ids)
    return CheckResult(True, f"VPC {vpc['VpcId']} has {len(subnets)} subnets in {len(azs)} AZs and {APP_SG}", ids)


def subnet_group_two_azs(ctx: CheckContext) -> CheckResult:
    vpc, group = _vpc(ctx), _subnet_group(ctx)
    if vpc is None:
        return _no_vpc()
    if group is None:
        return CheckResult(False, f"no DB subnet group named {SUBNET_GROUP} yet")
    ids = [group["DBSubnetGroupArn"]]
    if group.get("VpcId") != vpc["VpcId"]:
        return CheckResult(False, f"{SUBNET_GROUP} is in {group.get('VpcId')}, not the lab VPC {vpc['VpcId']}", ids)
    azs = sorted({s["SubnetAvailabilityZone"]["Name"] for s in group.get("Subnets") or []})
    if len(azs) < 2:
        return CheckResult(False, f"{SUBNET_GROUP} spans {len(azs)} AZ ({', '.join(azs) or 'none'}); RDS needs two", ids)
    return CheckResult(True, f"{SUBNET_GROUP} spans {', '.join(azs)}", ids)


def subnet_group_private(ctx: CheckContext) -> CheckResult:
    group = _subnet_group(ctx)
    if group is None:
        return CheckResult(False, f"no DB subnet group named {SUBNET_GROUP} yet")
    ids = [s["SubnetIdentifier"] for s in group.get("Subnets") or []]
    tables = ctx.client("ec2").describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [group["VpcId"]]}])["RouteTables"]
    explicit = {a["SubnetId"]: t for t in tables for a in t.get("Associations") or [] if a.get("SubnetId")}
    main = next((t for t in tables if any(a.get("Main") for a in t.get("Associations") or [])), None)
    public = [
        s for s in ids
        if any(r.get("DestinationCidrBlock") == "0.0.0.0/0" and str(r.get("GatewayId", "")).startswith("igw-")
               for r in (explicit.get(s) or main or {}).get("Routes") or [])
    ]
    if public:
        return CheckResult(False, f"subnet(s) {', '.join(public)} route to an Internet Gateway; keep the database private",
                           [group["DBSubnetGroupArn"], *public])
    return CheckResult(True, f"every subnet of {SUBNET_GROUP} is private", [group["DBSubnetGroupArn"], *ids])


def _opens_mysql(perm: dict) -> bool:
    if perm.get("IpProtocol") == "-1":
        return True
    return perm.get("IpProtocol") == "tcp" and (perm.get("FromPort") or 0) <= MYSQL_PORT <= (perm.get("ToPort") or 0)


def _inside_vpc(cidr: str) -> bool:
    try:
        return ipaddress.ip_network(cidr, strict=False).subnet_of(ipaddress.ip_network(VPC_CIDR))
    except (ValueError, TypeError):
        return False


def db_sg_mysql_from_app(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    db = _sg(ctx, vpc["VpcId"], DB_SG)
    if db is None:
        return CheckResult(False, f"no security group named {DB_SG} in the lab VPC yet")
    app = _sg(ctx, vpc["VpcId"], APP_SG)
    sources = []
    for perm in db.get("IpPermissions") or []:
        if _opens_mysql(perm):
            sources += [p["GroupId"] for p in perm.get("UserIdGroupPairs") or [] if app and p.get("GroupId") == app["GroupId"]]
            sources += [r["CidrIp"] for r in perm.get("IpRanges") or [] if _inside_vpc(r.get("CidrIp"))]
    if not sources:
        return CheckResult(False, f"{DB_SG} does not let tcp {MYSQL_PORT} in from {APP_SG} or the VPC range", [db["GroupId"]])
    return CheckResult(True, f"{DB_SG} lets tcp {MYSQL_PORT} in from {', '.join(sources)}", [db["GroupId"]])


def db_sg_not_open_to_world(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    db = _sg(ctx, vpc["VpcId"], DB_SG)
    if db is None:
        return CheckResult(False, f"no security group named {DB_SG} in the lab VPC yet")
    open_rules = [
        f"{p.get('IpProtocol')} {p.get('FromPort')}-{p.get('ToPort')}"
        for p in db.get("IpPermissions") or []
        if ({r.get("CidrIp") for r in p.get("IpRanges") or []} | {r.get("CidrIpv6") for r in p.get("Ipv6Ranges") or []}) & WORLD
    ]
    if open_rules:
        return CheckResult(False, f"{DB_SG} lets the internet in ({'; '.join(open_rules)})", [db["GroupId"]])
    return CheckResult(True, f"{DB_SG} lets nothing in from the internet", [db["GroupId"]])


def _no_rds() -> CheckResult:
    return CheckResult(False, f"no DB instance named {RDS_ID} yet")


def rds_mysql_available(ctx: CheckContext, instance_class: str) -> CheckResult:
    db = _instance(ctx, RDS_ID)
    if db is None:
        return _no_rds()
    ids, problems = [db["DBInstanceArn"]], []
    if db.get("Engine") != "mysql":
        problems.append(f"engine {db.get('Engine')}, expected mysql")
    if db.get("DBInstanceClass") != instance_class:
        problems.append(f"class {db.get('DBInstanceClass')}, expected {instance_class}")
    if db.get("DBInstanceStatus") != "available":
        problems.append(f"status {db.get('DBInstanceStatus')}, wait for available")
    if problems:
        return CheckResult(False, f"{RDS_ID}: {'; '.join(problems)}", ids)
    return CheckResult(True, f"{RDS_ID} is an available mysql {instance_class}", ids)


def rds_mysql_private(ctx: CheckContext) -> CheckResult:
    db = _instance(ctx, RDS_ID)
    if db is None:
        return _no_rds()
    vpc = _vpc(ctx)
    sg = _sg(ctx, vpc["VpcId"], DB_SG) if vpc else None
    attached = [g["VpcSecurityGroupId"] for g in db.get("VpcSecurityGroups") or []]
    problems = []
    if db.get("PubliclyAccessible"):
        problems.append("it is publicly accessible")
    if db.get("MultiAZ"):
        problems.append("it is Multi-AZ; this lab compares a single-AZ instance")
    if (db.get("DBSubnetGroup") or {}).get("DBSubnetGroupName") != SUBNET_GROUP:
        problems.append(f"it is not in {SUBNET_GROUP}")
    if sg is None or sg["GroupId"] not in attached:
        problems.append(f"{DB_SG} is not attached")
    ids = [db["DBInstanceArn"], *attached]
    if problems:
        return CheckResult(False, f"{RDS_ID}: {'; '.join(problems)}", ids)
    return CheckResult(True, f"{RDS_ID} is single-AZ, private, in {SUBNET_GROUP} behind {DB_SG}", ids)


def rds_mysql_storage_autoscaling(ctx: CheckContext, allocated: int, max_allocated: int) -> CheckResult:
    db = _instance(ctx, RDS_ID)
    if db is None:
        return _no_rds()
    size, ceiling = db.get("AllocatedStorage"), db.get("MaxAllocatedStorage")
    if size != allocated or ceiling != max_allocated:
        return CheckResult(False, f"{RDS_ID} has {size} GiB growing to {ceiling or 'no limit set'}; "
                                  f"expected {allocated} GiB growing to {max_allocated} GiB", [db["DBInstanceArn"]])
    return CheckResult(True, f"{RDS_ID} has {size} GiB and may grow to {ceiling} GiB", [db["DBInstanceArn"]])


def rds_mysql_gp3(ctx: CheckContext) -> CheckResult:
    db = _instance(ctx, RDS_ID)
    if db is None:
        return CheckResult(False, f"no DB instance named {RDS_ID} yet", info=True)
    kind = db.get("StorageType")
    if kind == "gp3":
        return CheckResult(True, f"{RDS_ID} uses gp3", [db["DBInstanceArn"]], info=True)
    return CheckResult(False, f"{RDS_ID} reports {kind}; Floci 2.3.0 reports gp2 whatever StorageType you ask for, "
                              "so this is not graded", [db["DBInstanceArn"]], info=True)


def aurora_cluster(ctx: CheckContext) -> CheckResult:
    cluster = _cluster(ctx)
    if cluster is None:
        return CheckResult(False, f"no DB cluster named {CLUSTER_ID} yet")
    problems = []
    if cluster.get("Engine") != "aurora-mysql":
        problems.append(f"engine {cluster.get('Engine')}, expected aurora-mysql")
    if cluster.get("DBSubnetGroup") != SUBNET_GROUP:
        problems.append(f"subnet group {cluster.get('DBSubnetGroup')}, expected {SUBNET_GROUP}")
    if cluster.get("Status") != "available":
        problems.append(f"status {cluster.get('Status')}, wait for available")
    ids = [cluster["DBClusterArn"]]
    if problems:
        return CheckResult(False, f"{CLUSTER_ID}: {'; '.join(problems)}", ids)
    return CheckResult(True, f"{CLUSTER_ID} is an available aurora-mysql cluster in {SUBNET_GROUP}", ids)


def _members(ctx: CheckContext, cluster: dict) -> list[tuple[dict, dict | None]]:
    return [(m, _instance(ctx, m["DBInstanceIdentifier"])) for m in cluster.get("DBClusterMembers") or []]


def aurora_writer_reader(ctx: CheckContext) -> CheckResult:
    cluster = _cluster(ctx)
    if cluster is None:
        return CheckResult(False, f"no DB cluster named {CLUSTER_ID} yet")
    members = _members(ctx, cluster)
    ids = [cluster["DBClusterArn"], *(db["DBInstanceArn"] for _, db in members if db)]
    writers = sum(1 for m, _ in members if m.get("IsClusterWriter"))
    waiting = [m["DBInstanceIdentifier"] for m, db in members if not db or db.get("DBInstanceStatus") != "available"]
    if writers != 1 or len(members) - writers < 1:
        return CheckResult(False, f"{CLUSTER_ID} has {writers} writer(s) and {len(members) - writers} reader(s); "
                                  "add instances with --db-cluster-identifier until there is a writer and a reader", ids)
    if waiting:
        return CheckResult(False, f"{', '.join(waiting)} not available yet", ids)
    return CheckResult(True, f"{CLUSTER_ID} has one writer and {len(members) - 1} reader(s), all available", ids)


def credentials_secret(ctx: CheckContext) -> CheckResult:
    try:
        meta = ctx.client("secretsmanager").describe_secret(SecretId=SECRET)
    except ClientError:
        return CheckResult(False, f"no secret named {SECRET} yet")
    return CheckResult(True, f"secret {SECRET} exists", [meta["ARN"]])


def aurora_failed_over(ctx: CheckContext) -> CheckResult:
    cluster = _cluster(ctx)
    if cluster is None:
        return CheckResult(False, f"no DB cluster named {CLUSTER_ID} yet")
    members = [(m, db) for m, db in _members(ctx, cluster) if db]
    if len(members) < 2:
        return CheckResult(False, f"{CLUSTER_ID} needs a writer and a reader before a failover", [cluster["DBClusterArn"]])
    first = min(members, key=lambda p: str(p[1].get("InstanceCreateTime")))
    writer = next((db for m, db in members if m.get("IsClusterWriter")), None)
    ids = [cluster["DBClusterArn"], *([writer["DBInstanceArn"]] if writer else [])]
    if writer is None or writer["DBInstanceIdentifier"] == first[1]["DBInstanceIdentifier"]:
        return CheckResult(False, f"the writer is still {first[1]['DBInstanceIdentifier']}, the cluster's first instance; "
                                  f"run a failover on {CLUSTER_ID}", ids)
    return CheckResult(True, f"{writer['DBInstanceIdentifier']} took the writer role from {first[1]['DBInstanceIdentifier']}", ids)
