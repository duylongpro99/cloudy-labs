# Wave 2: network kinds (EFS, ELBv2, Auto Scaling, Route 53)

## Outcome

I added eleven kinds in four new registry files. They all load. All 26 builder ops, rendered by the builder, ran with exit 0 against live Floci. A live collect over Floci gave no warnings and resolved every parent and edge, including the record-set alias to the load balancer, a zone associated with two VPCs, and target health. The `build_network` below was run end to end on live Floci, renamed to `pb-net-w2-` in 10.90.0.0/16, then collected (11 kinds, every edge resolved, no warnings) and deleted.

The full suite gives 657 passed and 2 failed. Both failures are the expected export diffs listed under Tests. All `pb-net-` probe resources are deleted, including the three instances (all `terminated`).

Files (all new):
- `server/src/cloudy_labs/registry/efs.yaml` (148 lines)
- `server/src/cloudy_labs/registry/elbv2.yaml` (219 lines)
- `server/src/cloudy_labs/registry/autoscaling.yaml` (115 lines)
- `server/src/cloudy_labs/registry/route53.yaml` (83 lines)

## Kinds added

| kind | parent | edges | ops | contract | view order |
|---|---|---|---|---|---|
| `efs-file-system` | region | none | create-file-system, update-file-system, put-lifecycle-configuration, put-backup-policy | create, then lifecycle and backup policy | 87 |
| `efs-mount-target` (listed per file system) | subnet (SubnetId) | `mount-of` to efs-file-system (reference); `attached` from security-group (reverse, attach) | create-mount-target (container SubnetId), modify-mount-target-security-groups | VPC 10.88, subnet, SG and file system, then create; parent subnet | 88 |
| `efs-access-point` | region | `access-point-of` to efs-file-system (reference) | create-access-point | needs a file system | 89 |
| `load-balancer` | vpc | `lb-subnet` to subnet (association); `attached` from security-group (reverse, attach) | create-load-balancer, set-security-groups, set-subnets | VPC 10.89, two subnets and an SG; then set-security-groups | 55 |
| `target-group` | vpc, else region | `uses-target-group` from load-balancer (reverse, via LoadBalancerArns); `registered-target` to instance or lambda-function (via DescribeTargetHealth) | create-target-group (container VpcId), register-targets, deregister-targets, modify-target-group | VPC 10.92; then modify-target-group | 56 |
| `listener` (listed per load balancer) | region | `listener-of` to load-balancer; `forwards-to` target-group (default action, including ForwardConfig) | create-listener, modify-listener | VPC 10.93, LB and TG; port 18081, then modified to 18082 | 57 |
| `listener-rule` (listed per listener, default rule hidden) | region | `rule-of` to listener; `forwards-to` target-group | create-rule, modify-rule | VPC 10.94, listener on 18083 with a fixed response | 58 |
| `autoscaling-group` | region | `uses-launch-template` (including MixedInstancesPolicy); `asg-instance` to instance; `asg-target-group` to target-group | create-auto-scaling-group, update-auto-scaling-group, set-desired-capacity, attach-load-balancer-target-groups (connect) | VPC 10.95, one subnet and a launch template; desired 0, then MaxSize 2 | 65 |
| `scaling-policy` | region | `policy-of` to autoscaling-group (matched by name); `alarm-action` from cloudwatch-alarm (reverse) | put-scaling-policy | VPC 10.96 and an ASG; target tracking at 50% CPU | 66 |
| `hosted-zone` (scope global) | global | `zone-vpc` to vpc (association, via GetHostedZone VPCs) | create-hosted-zone, associate-vpc-with-hosted-zone (connect), change-resource-record-sets (attribute) | VPC 10.97, private zone `ct.internal`; then UPSERT an A record | 106 |
| `record-set` (scope global, listed per zone, SOA/NS hidden) | global | `record-of` to hosted-zone; `alias-to` load-balancer (matched by DNSName with or without a trailing dot and `dualstack.`) | none; records are made by the zone's change-resource-record-sets | covered by the hosted-zone contract | 107 |

Notes:
- **Props.** All props are camelCase JMESPath. Every chat_props list holds settings only, with no secrets.
- **Tags.** load-balancer and target-group read their tags through DescribeTags enrich. efs-file-system, efs-access-point and autoscaling-group use `common.tags`.
- **Op text.** Each op has an English `note` and a Vietnamese `title`.
- **Icons.** Every icon is a real file under `aws-icon-pkg`, and none were copied:
  - EFS File-System
  - VPC Elastic-Network-Interface
  - Arch EFS
  - Arch ELB
  - Res Servers
  - Res Data-Stream
  - Res Document
  - EC2 Auto-Scaling
  - Res Metrics
  - Route-53 Hosted-Zone
  - Route-53 Route-Table
- **View orders.** The new orders (55–58, 65–66, 87–89, 106–107) do not collide with any order in the registry.
- **record-set has no create op.** ChangeResourceRecordSets returns only a ChangeInfo id. Its request has no single record name, so there is nothing a create expectation could check, and a create op without one fails the contract test. I made it an `attribute` op on `hosted-zone` instead (target_param HostedZoneId). The hosted-zone contract runs it, and the expectation is `{after: 1}`. record-set therefore is not `builder: true` itself. It is still drawn and checkable.

## APIs probed and Floci 2.3.0 quirks

Probed live through the wrapper:
- **EFS:** CreateFileSystem, DescribeFileSystems, UpdateFileSystem, Put/DescribeLifecycleConfiguration, Put/DescribeBackupPolicy, Create/Describe/DeleteMountTarget, Describe/ModifyMountTargetSecurityGroups, Create/Describe/DeleteAccessPoint, DeleteFileSystem.
- **ELBv2:**
  - Load balancers: Create/Describe/DeleteLoadBalancer, SetSecurityGroups, SetSubnets.
  - Target groups: Create/Describe/Modify/DeleteTargetGroup, Register/DeregisterTargets, DescribeTargetHealth, DescribeTags.
  - Listeners and rules: Create/Describe/Modify/DeleteListener, Create/Describe/Modify/DeleteRule.
- **Auto Scaling:** Create/Describe/Update/DeleteAutoScalingGroup, SetDesiredCapacity, AttachLoadBalancerTargetGroups, Put/Describe/DeletePolicy.
- **Route 53:** Create/List/Get/DeleteHostedZone, Associate/DisassociateVPCWithHostedZone, ChangeResourceRecordSets, ListResourceRecordSets. TestDNSAnswer is refused.

Quirks. Each one is either reflected in a caveat or worked around in the YAML.

- **EFS**
  - There is no NFS data plane.
  - The backup policy reads ENABLED on a new file system.
  - Every mount target reports IP 10.0.0.10, VPC `vpc-12345678` and AZ `<region>a`, whatever its subnet. I dropped the `az` prop, and the mount target's label uses the subnet id.
  - CreateMountTarget accepts a subnet id that does not exist.
- **ELBv2**
  - HTTP listeners really forward, but only to healthy targets; otherwise they return 503. From an instance container, `curl http://alb.<zone>:18080/` returned 200.
  - Listener ports are bound inside the Floci container and are not published to the host.
  - NLB/TCP and HTTPS forwarding are not emulated.
  - Floci returns the default rule from DescribeRules (it is filtered out by `IsDefault`).
  - RegisterTargets accepts an instance id that does not exist.
  - The LB DNS name is `<name>-<hash>.elb.localhost.floci.io`, and `CanonicalHostedZoneId` is returned.
- **Auto Scaling**
  - The reconciler really launches instances, which are real containers.
  - Instances get no `aws:autoscaling:groupName` tag.
  - ELB health never replaces an instance.
  - A target that you register by hand into a target group the ASG owns is dropped on the next reconcile.
  - The group ARN has no UUID.
  - `AvailabilityZones` is empty.
  - `LaunchTemplate.LaunchTemplateName` is missing from the description. The prop is null, and the edge uses the id.
  - Policies are stored but never executed, and target tracking creates no alarms.
  - A target-tracking policy reports `ScalingAdjustment: 0`.
- **Route 53**
  - Zones always contain NS and SOA records.
  - An alias DNSName is stored verbatim, without a trailing dot. The edge match covers both forms.
  - DNS is answered only for private zones, only for A records (CNAME and alias are followed), and for every VPC alike. From an instance container, `getent` resolved A, CNAME and alias records, with the alias going to the Floci IP. A public zone is never answered.

## Caveats added

- `efs-no-data-plane`, `flag-only` (lifecycle), `efs-backup-default` (backup) on efs-file-system.
- `efs-fake-ip` (ipAddress) on efs-mount-target.
- `elb-http-only` on load-balancer.
- `elb-accepts-unknown-targets` (targets) on target-group.
- `asg-no-elb-health` (healthCheckType) and `asg-no-group-tag` on autoscaling-group.
- `control-plane-only` on scaling-policy.
- `route53-private-dns-only` on hosted-zone (prop `private`) and on record-set.

## Hook and schema needs (not done; outside my file ownership)

1. **ASG subnets.** `VPCZoneIdentifier` is one comma-separated string. JMESPath cannot split it, so there is no autoscaling-group → subnet edge, and the group cannot sit under its VPC.
   - Need: a hook (for example `autoscaling.subnets`) that returns `VPCZoneIdentifier.split(",")`. Use it for a `group-subnet` association edge and for a `subnets` list prop. Optionally add a parent hook that returns the subnets' VPC.
2. **Sanitize rejects multi-subnet ASGs.** In `builder/sanitize.py`, `NAME_FIELDS` (`(?:^|[a-z])(?:Name|Identifier)$`) matches `VPCZoneIdentifier` and rejects the comma. As a result, the builder cannot create a group in two subnets, which is the normal case, and both ASG contracts use one subnet.
   - Need: exempt `VPCZoneIdentifier`, or let a field declare itself a comma-separated id list.
3. **No create expectation for records.** A ChangeResourceRecordSets create has no result id or label that the op schema can point at (the name is inside the ChangeBatch JSON).
   - If a "record" create gesture is wanted, the schema needs an expectation path into a JSON field, for example `expect: {label_from: ChangeBatch.Changes.0.ResourceRecordSet.Name}`. Until then it is an attribute op on the zone.
4. **Zone label and the trailing dot.** Hosted-zone and record labels keep Route 53's trailing dot (`ct.internal.`). So `create-hosted-zone` has no `expect.label`, because the learner types `ct.internal`.
   - Need: a `common.strip_dot`-style hook, or a label normaliser, so that names compare without the dot.
5. **EFS label fallback.** An EFS file system shows its CreationToken until a Name tag is set. This is intended and is stated in the op note. No change is needed, but checks should key on CreationToken, not the label.
6. **Recorder kinds.** `record-floci-fixtures.py` `wave_2_kinds()` records only the services that are not in `SERVICES`. EFS, ELBv2, Auto Scaling and Route 53 are therefore recorded. But vpc, subnet, security-group, launch-template and instance belong to `ec2` and are not recorded.
   - Effects: the recorded wave-2 fixture will have the LB, TG and mount-target parents fall back, and the `lb-subnet`, `attached`, `zone-vpc` and `uses-launch-template` edges dangle.
   - Need: add those ec2 kinds to `WAVE_2_EXTRA_KINDS`.

## Tests

- `uv run pytest -q`: **657 passed, 2 failed**, 92 deselected. Both failures are the expected export diffs:
  - `tests/test_app.py::test_registry_endpoint_matches_the_golden_and_the_web_copy`: the registry.json golden and web copy need re-exporting with the new kinds.
  - `tests/test_coverage.py::test_the_committed_matrix_is_what_the_generator_writes`: the committed coverage matrix needs regenerating.
- I fixed one failure of my own. `test_every_kind_the_builder_creates_declares_a_contract_of_ops_that_exist` failed with "record-set has a create op but no contract", which is why the op moved to hosted-zone.
- `tests/test_registry.py::test_every_service_failing_raises` failed once with "no fake client for autoscaling". Someone else then changed it to pass `kinds=LAB_KINDS`, and it now passes. I did not touch it.
- I did not run any `docker`-marked tests, `labctl` or the recorder.

## Ready-to-paste scenario

This function was verified on live Floci. Desired capacity is 0, so it launches no instance containers. As a result the `asg-instance` and `registered-target` edges are not in the fixture. To get them, set `DesiredCapacity=1`; the group will then register its instance in `w2-tg`. The listener port is 18091, because Floci binds every listener port inside its one container.

```python
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
```

Status: DONE_WITH_CONCERNS
Summary: Eleven network kinds were added in efs/elbv2/autoscaling/route53.yaml. All ops ran on live Floci, a live collect resolved every parent and edge, and the full suite has only the two expected export-diff failures. All probe resources are deleted.
Concerns:
- The registry.json golden, web copy and coverage matrix need regenerating.
- An ASG subnet edge needs a split hook.
- `builder/sanitize.py` wrongly treats `VPCZoneIdentifier` as a name field, so the builder cannot create multi-subnet groups.
- The recorder's `WAVE_2_EXTRA_KINDS` needs the ec2 network kinds for this scenario's parents and edges to land in the fixture.
