"""Build a representative scenario on a fresh Floci, then record what the collector reads.

    uv run python scripts/record-floci-fixtures.py build    # once, on an empty Floci (labctl up)
    uv run python scripts/record-floci-fixtures.py record   # writes tests/fixtures/graph/floci-describe/<service>/

    uv run python scripts/record-floci-fixtures.py build-reachability    # on another empty Floci
    uv run python scripts/record-floci-fixtures.py record-reachability   # writes tests/fixtures/reachability/floci/<service>/

    uv run python scripts/record-floci-fixtures.py build-wave-2    # on another empty Floci
    uv run python scripts/record-floci-fixtures.py record-wave-2   # writes tests/fixtures/graph/floci-describe-wave-2/

    uv run python scripts/record-floci-fixtures.py build-wave-3    # on another empty Floci
    uv run python scripts/record-floci-fixtures.py record-wave-3   # writes tests/fixtures/graph/floci-describe-wave-3/

Each recording also writes `kinds.json`, the kinds it listed. Replays list only those, so kinds
added to the registry later do not ask a recording for calls it never made.

`record` runs the real collector over the kinds of the EC2/VPC, RDS, S3, Lambda and IAM registry
entries, through clients that keep every call. Each `<service>/<method>.json` holds the calls in the
order made: `{"calls": [{"params": ..., "response": ...} | {"params": ..., "error": "Code"}]}`.
Tests replay them with `tests/graph_fixtures.FixtureClients`. Floci's ids are random, so re-recording
changes ids in the golden graph too; regenerate it from the replay with
`UPDATE_GOLDEN=1 uv run pytest tests/test_collector_replay.py`. Lambda environment values are
replaced before writing: a recording must never carry a secret someone put there.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from botocore.config import Config
from botocore.exceptions import ClientError

from cloudy_labs.builder.samples import sample_zip
from cloudy_labs.config import DEFAULT_REGION
from cloudy_labs.graph.collector import collect
from cloudy_labs.providers.aws import AwsProvider
from cloudy_labs.registry import default_registry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "graph" / "floci-describe"
WAVE_2_OUT = ROOT / "tests" / "fixtures" / "graph" / "floci-describe-wave-2"
WAVE_3_OUT = ROOT / "tests" / "fixtures" / "graph" / "floci-describe-wave-3"
# The wave-2 scenario also uses a bucket, a role and a small network; they are recorded so its
# parents and edges have both ends.
WAVE_2_EXTRA_KINDS = ("s3-bucket", "iam-role", "vpc", "subnet-public", "subnet-private", "security-group", "launch-template", "instance")
REACH_OUT = ROOT / "tests" / "fixtures" / "reachability" / "floci"
SERVICES = ("ec2", "rds", "s3", "lambda", "iam")
R = DEFAULT_REGION
CFG = Config(retries={"max_attempts": 1}, read_timeout=120)
PASSWORD = "Wave1-not-a-secret"  # Floci's databases are throwaway; the password never reaches the graph


def _client(service: str, region: str = R) -> Any:
    return AwsProvider("floci", region).client(service, direct=True, config=CFG)


def _tag(name: str, kind: str) -> list[dict]:
    return [{"ResourceType": kind, "Tags": [{"Key": "Name", "Value": name}]}]


def build() -> None:
    ec2, rds, s3, lam, iam = (_client(s) for s in SERVICES)
    if ec2.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": ["wave1-a"]}])["Vpcs"]:
        sys.exit("the scenario is already built; start from a fresh Floci (labctl down && labctl up)")
    acct = _client("sts").get_caller_identity()["Account"]

    # EC2 / VPC
    vpc_a = ec2.create_vpc(CidrBlock="10.80.0.0/16", TagSpecifications=_tag("wave1-a", "vpc"))["Vpc"]["VpcId"]
    vpc_b = ec2.create_vpc(CidrBlock="10.81.0.0/16", TagSpecifications=_tag("wave1-b", "vpc"))["Vpc"]["VpcId"]
    a1 = ec2.create_subnet(VpcId=vpc_a, CidrBlock="10.80.1.0/24", AvailabilityZone=R + "a", TagSpecifications=_tag("wave1-a1", "subnet"))["Subnet"]["SubnetId"]
    a2 = ec2.create_subnet(VpcId=vpc_a, CidrBlock="10.80.2.0/24", AvailabilityZone=R + "b", TagSpecifications=_tag("wave1-a2", "subnet"))["Subnet"]["SubnetId"]
    b1 = ec2.create_subnet(VpcId=vpc_b, CidrBlock="10.81.1.0/24", AvailabilityZone=R + "a", TagSpecifications=_tag("wave1-b1", "subnet"))["Subnet"]["SubnetId"]
    igw = ec2.create_internet_gateway(TagSpecifications=_tag("wave1-igw", "internet-gateway"))["InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=igw, VpcId=vpc_a)
    rt = ec2.create_route_table(VpcId=vpc_a, TagSpecifications=_tag("wave1-public-rt", "route-table"))["RouteTable"]["RouteTableId"]
    ec2.create_route(RouteTableId=rt, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw)
    ec2.associate_route_table(RouteTableId=rt, SubnetId=a1)

    acl = ec2.create_network_acl(VpcId=vpc_a, TagSpecifications=_tag("wave1-acl", "network-acl"))["NetworkAcl"]["NetworkAclId"]
    ec2.create_network_acl_entry(NetworkAclId=acl, RuleNumber=100, Protocol="6", RuleAction="allow", Egress=False, CidrBlock="0.0.0.0/0", PortRange={"From": 443, "To": 443})
    ec2.create_network_acl_entry(NetworkAclId=acl, RuleNumber=110, Protocol="6", RuleAction="deny", Egress=False, CidrBlock="0.0.0.0/0", PortRange={"From": 22, "To": 22})
    ec2.create_network_acl_entry(NetworkAclId=acl, RuleNumber=100, Protocol="-1", RuleAction="allow", Egress=True, CidrBlock="0.0.0.0/0")
    assoc = [x for n in ec2.describe_network_acls(Filters=[{"Name": "vpc-id", "Values": [vpc_a]}])["NetworkAcls"]
             for x in n.get("Associations", []) if x["SubnetId"] == a2]
    if assoc:
        ec2.replace_network_acl_association(AssociationId=assoc[0]["NetworkAclAssociationId"], NetworkAclId=acl)

    pl = ec2.create_managed_prefix_list(PrefixListName="wave1-office", MaxEntries=5, AddressFamily="IPv4",
                                        Entries=[{"Cidr": "203.0.113.0/24", "Description": "office"}])["PrefixList"]["PrefixListId"]
    app = ec2.create_security_group(GroupName="wave1-app", Description="app tier", VpcId=vpc_a)["GroupId"]
    web = ec2.create_security_group(GroupName="wave1-web", Description="web tier", VpcId=vpc_a)["GroupId"]
    ec2.authorize_security_group_ingress(GroupId=web, IpPermissions=[
        {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "PrefixListIds": [{"PrefixListId": pl}]}])
    ec2.authorize_security_group_ingress(GroupId=app, IpPermissions=[
        {"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432, "UserIdGroupPairs": [{"GroupId": web}]}])
    ec2.authorize_security_group_egress(GroupId=web, IpPermissions=[
        {"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432, "UserIdGroupPairs": [{"GroupId": app}]}])

    ec2.create_vpc_endpoint(VpcId=vpc_a, ServiceName=f"com.amazonaws.{R}.s3", VpcEndpointType="Gateway", RouteTableIds=[rt],
                            TagSpecifications=_tag("wave1-s3-endpoint", "vpc-endpoint"))
    ec2.create_vpc_endpoint(VpcId=vpc_a, ServiceName=f"com.amazonaws.{R}.sqs", VpcEndpointType="Interface", SubnetIds=[a2],
                            SecurityGroupIds=[app], TagSpecifications=_tag("wave1-sqs-endpoint", "vpc-endpoint"))
    pcx = ec2.create_vpc_peering_connection(VpcId=vpc_a, PeerVpcId=vpc_b, TagSpecifications=_tag("wave1-peering", "vpc-peering-connection"))["VpcPeeringConnection"]["VpcPeeringConnectionId"]
    ec2.accept_vpc_peering_connection(VpcPeeringConnectionId=pcx)
    ec2.create_route(RouteTableId=rt, DestinationCidrBlock="10.81.0.0/16", VpcPeeringConnectionId=pcx)
    ec2.create_flow_logs(ResourceIds=[vpc_a], ResourceType="VPC", TrafficType="REJECT", LogDestinationType="s3",
                         LogDestination="arn:aws:s3:::wave1-logs", TagSpecifications=_tag("wave1-flow", "vpc-flow-log"))

    tgw = ec2.create_transit_gateway(Description="wave1", TagSpecifications=_tag("wave1-tgw", "transit-gateway"))["TransitGateway"]["TransitGatewayId"]
    for _ in range(30):
        if ec2.describe_transit_gateways(TransitGatewayIds=[tgw])["TransitGateways"][0]["State"] == "available":
            break
        time.sleep(1)
    att_b = ec2.create_transit_gateway_vpc_attachment(TransitGatewayId=tgw, VpcId=vpc_b, SubnetIds=[b1],
                                                      TagSpecifications=_tag("wave1-tgw-b", "transit-gateway-attachment"))["TransitGatewayVpcAttachment"]["TransitGatewayAttachmentId"]
    tgw_rt = ec2.create_transit_gateway_route_table(TransitGatewayId=tgw, TagSpecifications=_tag("wave1-tgw-rt", "transit-gateway-route-table"))["TransitGatewayRouteTable"]["TransitGatewayRouteTableId"]
    # The extra table learns VPC B by propagation and holds a static route and a blackhole.
    ec2.enable_transit_gateway_route_table_propagation(TransitGatewayRouteTableId=tgw_rt, TransitGatewayAttachmentId=att_b)
    ec2.create_transit_gateway_route(TransitGatewayRouteTableId=tgw_rt, DestinationCidrBlock="10.90.0.0/16", TransitGatewayAttachmentId=att_b)
    ec2.create_transit_gateway_route(TransitGatewayRouteTableId=tgw_rt, DestinationCidrBlock="10.91.0.0/16", Blackhole=True)

    ec2.create_network_interface(SubnetId=a2, Groups=[app], Description="wave1 eni",
                                 TagSpecifications=_tag("wave1-eni", "network-interface"))
    vol = ec2.create_volume(AvailabilityZone=R + "a", Size=8, TagSpecifications=_tag("wave1-data", "volume"))["VolumeId"]
    ec2.create_volume(AvailabilityZone=R + "b", Size=4, TagSpecifications=_tag("wave1-spare", "volume"))
    ec2.create_launch_template(LaunchTemplateName="wave1-lt", LaunchTemplateData={"InstanceType": "t3.micro"})
    img = ec2.describe_images()["Images"][0]["ImageId"]
    iid = ec2.run_instances(ImageId=img, InstanceType="t3.micro", MinCount=1, MaxCount=1, SubnetId=a1, SecurityGroupIds=[web],
                            TagSpecifications=_tag("wave1-web-1", "instance"))["Instances"][0]["InstanceId"]
    for _ in range(60):
        if ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["State"]["Name"] == "running":
            break
        time.sleep(1)
    ec2.attach_volume(VolumeId=vol, InstanceId=iid, Device="/dev/sdf")

    # IAM (global)
    trust_lambda = json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]})
    role_arn = iam.create_role(RoleName="wave1-lambda-role", AssumeRolePolicyDocument=trust_lambda)["Role"]["Arn"]
    user_arn = iam.create_user(UserName="wave1-dev")["User"]["Arn"]
    # A key the user stopped using: the graph shows its id and status, never its secret.
    old_key = iam.create_access_key(UserName="wave1-dev")["AccessKey"]["AccessKeyId"]
    iam.update_access_key(UserName="wave1-dev", AccessKeyId=old_key, Status="Inactive")
    trust_user = json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"AWS": user_arn}, "Action": "sts:AssumeRole"}]})
    iam.create_role(RoleName="wave1-ops", AssumeRolePolicyDocument=trust_user)
    iam.create_group(GroupName="wave1-devs")
    iam.add_user_to_group(GroupName="wave1-devs", UserName="wave1-dev")
    doc = json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*"}]})
    pol = iam.create_policy(PolicyName="wave1-read", PolicyDocument=doc)["Policy"]["Arn"]
    iam.attach_group_policy(GroupName="wave1-devs", PolicyArn=pol)
    iam.attach_role_policy(RoleName="wave1-ops", PolicyArn=pol)
    iam.attach_role_policy(RoleName="wave1-lambda-role", PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
    iam.create_instance_profile(InstanceProfileName="wave1-web-profile")
    iam.add_role_to_instance_profile(InstanceProfileName="wave1-web-profile", RoleName="wave1-ops")

    # Lambda
    code = sample_zip("hello-python").read_bytes()
    layer = lam.publish_layer_version(LayerName="wave1-layer", Content={"ZipFile": code}, CompatibleRuntimes=["python3.12"])["LayerVersionArn"]
    fn = lam.create_function(FunctionName="wave1-fn", Runtime="python3.12", Role=role_arn, Handler="lambda_function.lambda_handler",
                             Code={"ZipFile": code}, Layers=[layer], Environment={"Variables": {"STAGE": "test"}})["FunctionArn"]
    ver = lam.publish_version(FunctionName="wave1-fn")["Version"]
    lam.create_alias(FunctionName="wave1-fn", Name="live", FunctionVersion=ver)
    lam.create_function(FunctionName="wave1-vpc-fn", Runtime="python3.12", Role=role_arn, Handler="lambda_function.lambda_handler",
                        Code={"ZipFile": code}, VpcConfig={"SubnetIds": [a2], "SecurityGroupIds": [app]})

    # S3: buckets in this region, one elsewhere (left out of this region's graph)
    loc = {"LocationConstraint": R}
    for b in ("wave1-logs", "wave1-site", "wave1-src", "wave1-dst"):
        s3.create_bucket(Bucket=b, CreateBucketConfiguration=loc)
    _client("s3", "us-east-1").create_bucket(Bucket="wave1-elsewhere")
    s3.put_bucket_versioning(Bucket="wave1-logs", VersioningConfiguration={"Status": "Enabled"})
    s3.put_bucket_encryption(Bucket="wave1-logs", ServerSideEncryptionConfiguration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})
    s3.put_public_access_block(Bucket="wave1-logs", PublicAccessBlockConfiguration={"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_lifecycle_configuration(Bucket="wave1-logs", LifecycleConfiguration={"Rules": [{"ID": "expire", "Status": "Enabled", "Filter": {"Prefix": "tmp/"}, "Expiration": {"Days": 30},
                                                                                         "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}}]})
    for i in range(3):
        s3.put_object(Bucket="wave1-logs", Key=f"tmp/{i}.txt", Body=b"x")
    s3.create_multipart_upload(Bucket="wave1-logs", Key="tmp/big.bin")  # left incomplete on purpose
    s3.put_bucket_website(Bucket="wave1-site", WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}})
    s3.put_bucket_policy(Bucket="wave1-site", Policy=json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::wave1-site/*"}]}))
    for b in ("wave1-src", "wave1-dst"):
        s3.put_bucket_versioning(Bucket=b, VersioningConfiguration={"Status": "Enabled"})
    s3.put_bucket_replication(Bucket="wave1-src", ReplicationConfiguration={"Role": role_arn, "Rules": [
        {"ID": "all", "Status": "Enabled", "Priority": 1, "Filter": {}, "DeleteMarkerReplication": {"Status": "Disabled"},
         "Destination": {"Bucket": "arn:aws:s3:::wave1-dst"}}]})
    s3.put_bucket_notification_configuration(Bucket="wave1-src", NotificationConfiguration={"LambdaFunctionConfigurations": [
        {"Id": "on-put", "LambdaFunctionArn": fn, "Events": ["s3:ObjectCreated:*"]}]})

    # RDS: each database is a container, so this part takes a while
    sg = rds.create_db_subnet_group(DBSubnetGroupName="wave1-db", DBSubnetGroupDescription="wave1", SubnetIds=[a1, a2])["DBSubnetGroup"]["DBSubnetGroupName"]
    rds.create_db_parameter_group(DBParameterGroupName="wave1-pg16", DBParameterGroupFamily="postgres16", Description="wave1")
    rds.create_db_cluster_parameter_group(DBClusterParameterGroupName="wave1-aurora-pg16", DBParameterGroupFamily="aurora-postgresql16", Description="wave1")
    rds.create_option_group(OptionGroupName="wave1-og", EngineName="postgres", MajorEngineVersion="16", OptionGroupDescription="wave1")
    rds.create_db_instance(DBInstanceIdentifier="wave1-pg", Engine="postgres", DBInstanceClass="db.t3.micro", MasterUsername="wave1",
                           MasterUserPassword=PASSWORD, AllocatedStorage=20, DBSubnetGroupName=sg, VpcSecurityGroupIds=[app],
                           DBParameterGroupName="wave1-pg16", OptionGroupName="wave1-og", MultiAZ=True)
    rds.create_db_instance_read_replica(DBInstanceIdentifier="wave1-pg-rr", SourceDBInstanceIdentifier="wave1-pg")
    rds.create_db_snapshot(DBSnapshotIdentifier="wave1-pg-snap", DBInstanceIdentifier="wave1-pg")
    rds.create_db_cluster(DBClusterIdentifier="wave1-aurora", Engine="aurora-postgresql", MasterUsername="wave1", MasterUserPassword=PASSWORD,
                          DBSubnetGroupName=sg, VpcSecurityGroupIds=[app], DBClusterParameterGroupName="wave1-aurora-pg16")
    rds.create_db_instance(DBInstanceIdentifier="wave1-aurora-1", Engine="aurora-postgresql", DBInstanceClass="db.t3.medium", DBClusterIdentifier="wave1-aurora")
    rds.create_db_cluster_snapshot(DBClusterSnapshotIdentifier="wave1-aurora-snap", DBClusterIdentifier="wave1-aurora")
    rds.create_db_proxy(DBProxyName="wave1-proxy", EngineFamily="POSTGRESQL", RoleArn=role_arn, VpcSubnetIds=[a1, a2], VpcSecurityGroupIds=[app],
                        Auth=[{"AuthScheme": "SECRETS", "SecretArn": f"arn:aws:secretsmanager:{R}:{acct}:secret:wave1-db", "IAMAuth": "DISABLED"}])
    rds.register_db_proxy_targets(DBProxyName="wave1-proxy", DBInstanceIdentifiers=["wave1-pg"])
    print("built")


def _wait(check, what: str, seconds: int = 60) -> None:
    for _ in range(seconds):
        if check():
            return
        time.sleep(1)
    sys.exit(f"timed out waiting for {what}")


def build_reachability() -> None:
    """The network the reachability scenario table (tests/fixtures/reachability/scenarios.yaml) is
    judged against: one case per way traffic can pass or be stopped. Hosts are ENIs where a
    container is not needed; one instance holds the public IP."""
    ec2, rds = _client("ec2"), _client("rds")
    if ec2.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": ["rx-a"]}])["Vpcs"]:
        sys.exit("the scenario is already built; start from a fresh Floci (labctl down && labctl up)")

    def vpc(name, cidr):
        return ec2.create_vpc(CidrBlock=cidr, TagSpecifications=_tag(name, "vpc"))["Vpc"]["VpcId"]

    def subnet(name, vpc_id, cidr, az="a"):
        return ec2.create_subnet(VpcId=vpc_id, CidrBlock=cidr, AvailabilityZone=R + az, TagSpecifications=_tag(name, "subnet"))["Subnet"]["SubnetId"]

    def table(name, vpc_id, *subnets):
        rt = ec2.create_route_table(VpcId=vpc_id, TagSpecifications=_tag(name, "route-table"))["RouteTable"]["RouteTableId"]
        for s in subnets:
            ec2.associate_route_table(RouteTableId=rt, SubnetId=s)
        return rt

    def main_table(vpc_id):
        return ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}, {"Name": "association.main", "Values": ["true"]}])["RouteTables"][0]["RouteTableId"]

    def group(name, vpc_id, ingress=(), revoke_egress=False):
        gid = ec2.create_security_group(GroupName=name, Description=name, VpcId=vpc_id, TagSpecifications=_tag(name, "security-group"))["GroupId"]
        if ingress:
            ec2.authorize_security_group_ingress(GroupId=gid, IpPermissions=list(ingress))
        if revoke_egress:
            ec2.revoke_security_group_egress(GroupId=gid, IpPermissions=[{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}])
        return gid

    def eni(name, subnet_id, gid, ip):
        return ec2.create_network_interface(SubnetId=subnet_id, Groups=[gid], PrivateIpAddress=ip, Description=name,
                                            TagSpecifications=_tag(name, "network-interface"))["NetworkInterface"]["NetworkInterfaceId"]

    open_all = {"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}

    # VPC A: public, private behind a NAT, a custom NACL, a blackhole and a routing loop
    a = vpc("rx-a", "10.60.0.0/16")
    a_pub, a_priv = subnet("rx-a-pub", a, "10.60.1.0/24"), subnet("rx-a-priv", a, "10.60.2.0/24")
    a_priv2 = subnet("rx-a-priv2", a, "10.60.3.0/24", "b")
    a_nacl, a_black, a_loop = subnet("rx-a-nacl", a, "10.60.4.0/24"), subnet("rx-a-black", a, "10.60.5.0/24"), subnet("rx-a-loop", a, "10.60.6.0/24")
    igw = ec2.create_internet_gateway(TagSpecifications=_tag("rx-igw", "internet-gateway"))["InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=igw, VpcId=a)
    rt_pub = table("rx-rt-a-pub", a, a_pub)
    ec2.create_route(RouteTableId=rt_pub, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw)
    eip = ec2.allocate_address(Domain="vpc", TagSpecifications=_tag("rx-nat-eip", "elastic-ip"))["AllocationId"]
    nat = ec2.create_nat_gateway(SubnetId=a_pub, AllocationId=eip, TagSpecifications=_tag("rx-nat", "natgateway"))["NatGateway"]["NatGatewayId"]
    rt_priv = table("rx-rt-a-priv", a, a_priv)
    ec2.create_route(RouteTableId=rt_priv, DestinationCidrBlock="0.0.0.0/0", NatGatewayId=nat)

    acl = ec2.create_network_acl(VpcId=a, TagSpecifications=_tag("rx-acl", "network-acl"))["NetworkAcl"]["NetworkAclId"]
    ec2.create_tags(Resources=[acl], Tags=[{"Key": "Name", "Value": "rx-acl"}])  # Floci drops TagSpecifications here
    ec2.create_network_acl_entry(NetworkAclId=acl, RuleNumber=90, Protocol="6", RuleAction="deny", Egress=False, CidrBlock="0.0.0.0/0", PortRange={"From": 22, "To": 22})
    ec2.create_network_acl_entry(NetworkAclId=acl, RuleNumber=100, Protocol="6", RuleAction="allow", Egress=False, CidrBlock="0.0.0.0/0", PortRange={"From": 0, "To": 65535})
    ec2.create_network_acl_entry(NetworkAclId=acl, RuleNumber=100, Protocol="6", RuleAction="allow", Egress=True, CidrBlock="0.0.0.0/0", PortRange={"From": 0, "To": 1023})
    assoc = [x for n in ec2.describe_network_acls(Filters=[{"Name": "vpc-id", "Values": [a]}])["NetworkAcls"]
             for x in n.get("Associations", []) if x["SubnetId"] == a_nacl]
    ec2.replace_network_acl_association(AssociationId=assoc[0]["NetworkAclAssociationId"], NetworkAclId=acl)

    dead_eip = ec2.allocate_address(Domain="vpc")["AllocationId"]
    dead = ec2.create_nat_gateway(SubnetId=a_pub, AllocationId=dead_eip, TagSpecifications=_tag("rx-nat-dead", "natgateway"))["NatGateway"]["NatGatewayId"]
    rt_black = table("rx-rt-a-black", a, a_black)
    ec2.create_route(RouteTableId=rt_black, DestinationCidrBlock="0.0.0.0/0", NatGatewayId=dead)
    ec2.delete_nat_gateway(NatGatewayId=dead)  # the route stays: AWS marks it blackhole

    pl = ec2.create_managed_prefix_list(PrefixListName="rx-office", MaxEntries=5, AddressFamily="IPv4",
                                        Entries=[{"Cidr": "203.0.113.0/24", "Description": "office"}])["PrefixList"]["PrefixListId"]
    web = group("rx-sg-web", a, [{"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                                 {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "PrefixListIds": [{"PrefixListId": pl}]}])
    app = group("rx-sg-app", a, [{"IpProtocol": "tcp", "FromPort": 8080, "ToPort": 8080, "UserIdGroupPairs": [{"GroupId": web}]}])
    db = group("rx-sg-db", a, [{"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432, "UserIdGroupPairs": [{"GroupId": app}]}])
    locked = group("rx-sg-locked", a, revoke_egress=True)
    open_a = group("rx-sg-open-a", a, [open_all])

    eni("rx-app", a_priv, app, "10.60.2.10")
    eni("rx-locked", a_priv, locked, "10.60.2.11")
    eni("rx-a2-host", a_priv2, open_a, "10.60.3.10")
    eni("rx-nacl-host", a_nacl, open_a, "10.60.4.10")
    eni("rx-black-host", a_black, open_a, "10.60.5.10")
    eni("rx-loop-host", a_loop, open_a, "10.60.6.10")
    hop = eni("rx-loop-hop", a_loop, open_a, "10.60.6.11")
    rt_loop = table("rx-rt-a-loop", a, a_loop)
    ec2.create_route(RouteTableId=rt_loop, DestinationCidrBlock="0.0.0.0/0", NetworkInterfaceId=hop)
    ec2.create_vpc_endpoint(VpcId=a, ServiceName=f"com.amazonaws.{R}.s3", VpcEndpointType="Gateway", RouteTableIds=[rt_priv],
                            TagSpecifications=_tag("rx-s3-endpoint", "vpc-endpoint"))

    # VPC B and C: A-B and B-C peerings, so A cannot reach C through B
    b, c = vpc("rx-b", "10.61.0.0/16"), vpc("rx-c", "10.62.0.0/16")
    b1, c1 = subnet("rx-b1", b, "10.61.1.0/24"), subnet("rx-c1", c, "10.62.1.0/24")
    eni("rx-b-host", b1, group("rx-sg-open-b", b, [open_all]), "10.61.1.10")
    eni("rx-c-host", c1, group("rx-sg-open-c", c, [open_all]), "10.62.1.10")
    ab = ec2.create_vpc_peering_connection(VpcId=a, PeerVpcId=b, TagSpecifications=_tag("rx-pcx-ab", "vpc-peering-connection"))["VpcPeeringConnection"]["VpcPeeringConnectionId"]
    bc = ec2.create_vpc_peering_connection(VpcId=b, PeerVpcId=c, TagSpecifications=_tag("rx-pcx-bc", "vpc-peering-connection"))["VpcPeeringConnection"]["VpcPeeringConnectionId"]
    ec2.accept_vpc_peering_connection(VpcPeeringConnectionId=ab)
    ec2.accept_vpc_peering_connection(VpcPeeringConnectionId=bc)
    ec2.create_route(RouteTableId=rt_priv, DestinationCidrBlock="10.61.0.0/16", VpcPeeringConnectionId=ab)
    ec2.create_route(RouteTableId=rt_priv, DestinationCidrBlock="10.62.0.0/16", VpcPeeringConnectionId=ab)
    ec2.create_route(RouteTableId=main_table(b), DestinationCidrBlock="10.60.0.0/16", VpcPeeringConnectionId=ab)
    ec2.create_route(RouteTableId=main_table(b), DestinationCidrBlock="10.62.0.0/16", VpcPeeringConnectionId=bc)
    ec2.create_route(RouteTableId=main_table(c), DestinationCidrBlock="10.61.0.0/16", VpcPeeringConnectionId=bc)

    # VPC D and E behind a Transit Gateway with two route tables, a blackhole and a loop
    d, e = vpc("rx-d", "10.63.0.0/16"), vpc("rx-e", "10.64.0.0/16")
    d1, e1 = subnet("rx-d1", d, "10.63.1.0/24"), subnet("rx-e1", e, "10.64.1.0/24")
    eni("rx-d-host", d1, group("rx-sg-open-d", d, [open_all]), "10.63.1.10")
    eni("rx-e-host", e1, group("rx-sg-open-e", e, [open_all]), "10.64.1.10")
    tgw = ec2.create_transit_gateway(Description="reachability", TagSpecifications=_tag("rx-tgw", "transit-gateway"))["TransitGateway"]["TransitGatewayId"]
    _wait(lambda: ec2.describe_transit_gateways(TransitGatewayIds=[tgw])["TransitGateways"][0]["State"] == "available", "the transit gateway")
    att_d = ec2.create_transit_gateway_vpc_attachment(TransitGatewayId=tgw, VpcId=d, SubnetIds=[d1], TagSpecifications=_tag("rx-att-d", "transit-gateway-attachment"))["TransitGatewayVpcAttachment"]["TransitGatewayAttachmentId"]
    att_e = ec2.create_transit_gateway_vpc_attachment(TransitGatewayId=tgw, VpcId=e, SubnetIds=[e1], TagSpecifications=_tag("rx-att-e", "transit-gateway-attachment"))["TransitGatewayVpcAttachment"]["TransitGatewayAttachmentId"]
    default_rt = ec2.describe_transit_gateways(TransitGatewayIds=[tgw])["TransitGateways"][0]["Options"]["AssociationDefaultRouteTableId"]
    ec2.create_tags(Resources=[default_rt], Tags=[{"Key": "Name", "Value": "rx-tgw-rt-main"}])
    rt_e = ec2.create_transit_gateway_route_table(TransitGatewayId=tgw, TagSpecifications=_tag("rx-tgw-rt-e", "transit-gateway-route-table"))["TransitGatewayRouteTable"]["TransitGatewayRouteTableId"]
    _wait(lambda: ec2.describe_transit_gateway_route_tables(TransitGatewayRouteTableIds=[rt_e])["TransitGatewayRouteTables"][0]["State"] == "available", "the TGW route table")
    ec2.disassociate_transit_gateway_route_table(TransitGatewayRouteTableId=default_rt, TransitGatewayAttachmentId=att_e)
    ec2.associate_transit_gateway_route_table(TransitGatewayRouteTableId=rt_e, TransitGatewayAttachmentId=att_e)
    ec2.create_transit_gateway_route(TransitGatewayRouteTableId=default_rt, DestinationCidrBlock="10.64.0.0/16", TransitGatewayAttachmentId=att_e)
    ec2.create_transit_gateway_route(TransitGatewayRouteTableId=default_rt, DestinationCidrBlock="10.65.0.0/16", Blackhole=True)
    ec2.create_transit_gateway_route(TransitGatewayRouteTableId=default_rt, DestinationCidrBlock="10.99.0.0/16", TransitGatewayAttachmentId=att_d)
    ec2.create_transit_gateway_route(TransitGatewayRouteTableId=rt_e, DestinationCidrBlock="10.63.0.0/16", TransitGatewayAttachmentId=att_d)
    # Floci 2.3.0 keeps these routes but drops their TransitGatewayId; tests/fixtures/reachability/patches.yaml puts it back.
    for dest in ("10.64.0.0/16", "10.65.0.0/16", "10.99.0.0/16"):
        ec2.create_route(RouteTableId=main_table(d), DestinationCidrBlock=dest, TransitGatewayId=tgw)
    ec2.create_route(RouteTableId=main_table(e), DestinationCidrBlock="10.63.0.0/16", TransitGatewayId=tgw)

    for name, vpc_id in (("a", a), ("b", b), ("c", c), ("d", d), ("e", e)):
        ec2.create_tags(Resources=[main_table(vpc_id)], Tags=[{"Key": "Name", "Value": f"rx-rt-{name}-main"}])

    # The public web server (an instance, for its public IP) and a database behind sg-db
    img = ec2.describe_images()["Images"][0]["ImageId"]
    # Floci ignores Groups inside NetworkInterfaces (the instance lands in the default group), so the
    # group goes on the call and the public IP comes from the subnet setting.
    ec2.modify_subnet_attribute(SubnetId=a_pub, MapPublicIpOnLaunch={"Value": True})
    iid = ec2.run_instances(ImageId=img, InstanceType="t3.micro", MinCount=1, MaxCount=1, TagSpecifications=_tag("rx-web", "instance"),
                            SubnetId=a_pub, SecurityGroupIds=[web], PrivateIpAddress="10.60.1.10")["Instances"][0]["InstanceId"]
    _wait(lambda: ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["State"]["Name"] == "running", "the instance")
    rds.create_db_subnet_group(DBSubnetGroupName="rx-db", DBSubnetGroupDescription="reachability", SubnetIds=[a_priv, a_priv2])
    rds.create_db_instance(DBInstanceIdentifier="rx-db", Engine="postgres", DBInstanceClass="db.t3.micro", MasterUsername="rx",
                           MasterUserPassword=PASSWORD, AllocatedStorage=20, DBSubnetGroupName="rx-db", VpcSecurityGroupIds=[db],
                           AvailabilityZone=R + "a", PubliclyAccessible=False)
    print("built")


class Recorder:
    """A client that forwards every call and keeps (params, response or error code)."""

    def __init__(self, client: Any, calls: dict[str, list[dict]]):
        self._client, self._calls = client, calls

    def can_paginate(self, method: str) -> bool:
        return False  # one plain call per list, so a replay needs no paginator

    def __getattr__(self, name: str) -> Any:
        fn = getattr(self._client, name)
        if not callable(fn) or name.startswith("_"):
            return fn

        def call(**params: Any) -> Any:
            try:
                response = fn(**params)
            except ClientError as e:
                self._calls.setdefault(name, []).append({"params": params, "error": e.response["Error"]["Code"]})
                raise
            response.pop("ResponseMetadata", None)
            self._calls.setdefault(name, []).append({"params": params, "response": response})
            return response

        return call


class RecordingProvider(AwsProvider):
    def __init__(self) -> None:
        super().__init__("floci", R)
        self.calls: dict[str, dict[str, list[dict]]] = {}

    def client(self, service: str, *args: Any, **kwargs: Any) -> Any:
        return Recorder(super().client(service, *args, **kwargs), self.calls.setdefault(service, {}))


def _redact(value: Any) -> Any:
    """A copy with every Lambda Environment.Variables value and CodeBuild environmentVariables value
    replaced."""
    if isinstance(value, dict):
        out = {k: _redact(v) for k, v in value.items()}
        if isinstance(out.get("environmentVariables"), list):
            out["environmentVariables"] = [{**v, "value": "<redacted>"} if isinstance(v, dict) else v
                                           for v in out["environmentVariables"]]
        variables = (out.get("Environment") or {}).get("Variables") if isinstance(out.get("Environment"), dict) else None
        if isinstance(variables, dict):
            out["Environment"] = {**out["Environment"], "Variables": {k: "<redacted>" for k in variables}}
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"


def record(out: Path = OUT, kinds: list[str] | None = None) -> None:
    registry = default_registry()
    if kinds is None:
        kinds = [t.kind for t in registry.types if t.service in SERVICES and t.listing is not None]
    provider = RecordingProvider()
    graph = collect(provider, kinds=kinds, ports=lambda: {}, registry=registry)
    for service, methods in provider.calls.items():
        folder = out / service if service in SERVICES else out / "other" / service
        folder.mkdir(parents=True, exist_ok=True)
        for method, calls in methods.items():
            (folder / f"{method}.json").write_text(_json({"calls": _redact(calls)}))
    (out / "kinds.json").write_text(json.dumps(kinds, indent=2) + "\n")
    print(f"recorded {sum(len(c) for m in provider.calls.values() for c in m.values())} calls; "
          f"{len(graph.nodes)} nodes, {len(graph.edges)} edges, warnings: {graph.warnings}")


def build_wave(n: int) -> None:
    import importlib

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    scenario = importlib.import_module(f"floci_wave_{n}_scenario")

    for name in sorted(n for n in dir(scenario) if n.startswith("build_")):
        print(f"{name} ...")
        getattr(scenario, name)(_client)


def wave_2_kinds() -> list[str]:
    registry = default_registry()
    return [t.kind for t in registry.types
            if t.listing is not None and (t.service not in SERVICES or t.kind in WAVE_2_EXTRA_KINDS)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd in ("build", "record", "build-reachability", "record-reachability", "build-wave-2", "record-wave-2",
                "build-wave-3", "record-wave-3"):
        sub.add_parser(cmd)
    args = parser.parse_args()
    if args.cmd == "build":
        build()
    elif args.cmd == "record":
        record()
    elif args.cmd == "build-reachability":
        build_reachability()
    elif args.cmd == "build-wave-2":
        build_wave(2)
    elif args.cmd == "record-wave-2":
        record(WAVE_2_OUT, wave_2_kinds())
    elif args.cmd == "build-wave-3":
        build_wave(3)
    elif args.cmd == "record-wave-3":
        # The whole registry: the scenario links to kinds of every earlier wave.
        record(WAVE_3_OUT, [t.kind for t in default_registry().types if t.listing is not None])
    else:
        from cloudy_labs.reachability import NETWORK_KINDS

        record(REACH_OUT, list(NETWORK_KINDS))


if __name__ == "__main__":
    main()
