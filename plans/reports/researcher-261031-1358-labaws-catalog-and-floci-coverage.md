# labaws.site catalog vs Floci 2.3.0 coverage

Date: 2026-10-31. Researcher report, evidence only, no implementation.
Companion data: `researcher-261031-1358-labaws-catalog-and-floci-coverage.csv` (530 rows, one per lab).

## Bottom line

- labaws.site lists **530 labs** in 5 categories: DVA 130, Network 100, RDS 100, Storage 100 and SOA 100. Every lab says **ap-southeast-2 (Sydney)**, **Intermediate** and **45 min**. Those three values are identical on all 530 pages, so they look like template defaults rather than real per-lab data (inferred).
- The labs are **console-first**. 510 of 530 tables of contents name only the AWS Console for the steps. CLI shows up mostly in "$0.00 cleanup scripts", which appear in 297 labs. Only 21 tables of contents mention CLI or IaC in the body steps. Full step text is behind Google login and was not read.
- In **488 of 530 labs (92%)**, every service we detected exists as an API in Floci 2.3.0. The real gaps are **FSx, Storage Gateway, Direct Connect, Site-to-Site VPN/Customer Gateway, Client VPN, Snow Family, X-Ray, Amplify, and EBS `CreateSnapshot`**. These block 34 labs outright and degrade 8 more.
- An API existing does not mean the lab works. Floci does **not** emulate VPC routing, NACLs, NAT, or peering data paths. S3 replication is config-only. RDS/Aurora is a single MySQL/Postgres/MariaDB/SQL Server container. Another 73 labs, mostly Network and Storage, are therefore classed **control-plane-only**: you can create the resources, but the behaviour the lab teaches will not happen.
- **There is a "list all resources" endpoint, with limits.** Resource Groups Tagging `GetResources` lists **only tagged resources**. Resource Explorer 2 `ListResources`/`Search` queries live service state, but it covers only about 31 services and 8 EC2 types. NACLs, ENIs, EIPs, TGW, peering, endpoints, Route 53, EFS, ELB listeners and Auto Scaling groups are not in it.
- **ap-southeast-2 works.** Region scoping is per request. Each region seeds a default VPC on first access. Floci's default region is `us-east-1`, so set `FLOCI_DEFAULT_REGION=ap-southeast-2`.

## Part A: labaws.site catalog

### How the data was obtained (verified)

| Surface | Result |
|---|---|
| `https://labaws.site/robots.txt` | `Allow: /`, disallows `/callback` and `/login`, points to the sitemap |
| `https://labaws.site/sitemap.xml` | 534 URLs: 4 static pages and **530 `/labs/<slug>`** pages. `lastmod` is 2026-10-26 for 530 URLs and 2026-10-29 for 4 |
| `https://labaws.site/labs` | SPA (React/Vite) page with crawler text: "hơn 500 bài lab… Thực hành 100% trên AWS Sydney Region (ap-southeast-2)" |
| JSON API the listing calls | `https://j4uexieqdg.execute-api.ap-southeast-2.amazonaws.com/api/labs?limit=200&cursor=…` and `/api/categories`, found in `/assets/index-BIvU6xBc.js`. Both return **401 Unauthorized** without a Google-login bearer token. Not bypassed. |
| `/labs/<slug>` pages | Server-rendered `<main class="sr-crawler-content">` plus JSON-LD `TechArticle`. Each page carries the title, the badges (category, level, duration, region), "Dịch vụ trọng tâm", "Chi phí ước tính" and the full **TOC**. All 530 were fetched once at 4 parallel requests. |

The lab body and the `.md` download (`/api/labs/{slug}/content`, `/download`, served through S3 presigned URL) require login.

### Catalog shape

| Category (badge) | Labs | Top main services (keyword-derived) | Floci fit |
|---|---|---|---|
| DVA | 130 | Lambda 28, S3 13, DynamoDB 12, API Gateway 9, CodeSuite 9, CloudFormation 7 | 125 api-covered, 2 blocked, 2 degraded, 1 control-plane-only |
| Network | 100 | VPC 56, Transit Gateway 8, Route 53 7, S2S VPN 6, ELB 5, Direct Connect 3, Network Firewall 3 | 50 / 9 / 2 / **39** |
| RDS | 100 | RDS 72, Aurora 11, DMS 5, CloudWatch 4 | 93 / 0 / 0 / 7 |
| Storage | 100 | S3 20, EBS 12, FSx 11, EFS 10, Backup 9, DataSync 6, DMS 6 | 62 / **18** / 4 / 16 |
| SOA | 100 | EC2 10, S3 8, VPC 6, RDS 5, CloudWatch 5, IAM 5, SSM 5 | 85 / 5 / 0 / 10 |
| **Total** | **530** | | **415 / 34 / 8 / 73** |

Other catalog facts:

- **Lab numbers are not unique.** For example, `lab-001-*` exists in Network, RDS and Storage, and SOA/DVA use two-digit numbers. Use the slug as the ID.
- **The services field is mostly the category name.** "Dịch vụ trọng tâm" is a real service list only for 22 Network and 17 Storage labs. Everywhere else it just repeats the category, so services come from the title and TOC.
- **Costs are almost all free tier.** 491 labs say "Free Tier Eligible" and 21 more say "~$0.00".
- **About 74 titles are conceptual** ("So sánh", "Lựa chọn", "Thiết kế", "Phân tích", "vs", runbook, capstone). These may create few resources (inferred).

### Labs per AWS service (main = first service in the title; mentioned = anywhere in title, services field or TOC)

| Service | Main | Mentioned | Floci 2.3.0 |
|---|---|---|---|
| RDS (incl. engines, param/subnet groups, replicas) | 83 | 121 | Yes, 98 ops, real containers |
| VPC (subnet, RT, IGW, NAT, SG, NACL, endpoints, peering, flow logs) | 66 | 102 | API yes; behaviour partial |
| S3 | 43 | 81 | Yes, 58 ops |
| Lambda | 30 | 54 | Yes, 55 ops, real containers |
| EC2 | 20 | 52 | Yes, about 194 ops, Docker-backed instances |
| CloudWatch (metrics/alarms) | 11 | 30 | Yes, 11 ops |
| EBS | 16 | 28 | Volumes yes; **no CreateSnapshot/CopySnapshot** |
| EFS | 12 | 24 | Yes, 26 ops |
| IAM | 10 | 21 | Yes, 167 ops; enforcement off by default |
| CloudFormation | 10 | 21 | Yes, 36 ops |
| DynamoDB (+Streams) | 16 | 20 | Yes, 28 + 4 |
| Aurora | 14 | 19 | Control plane yes (clusters, global, serverless v2 shape); runs plain MySQL/PG |
| KMS | 4 | 19 | Yes, 42 |
| **FSx** | 13 | 18 | **Missing** |
| SSM (Parameter Store, Run Command) | 7 | 17 | Yes, 22 |
| ELB/ALB/NLB | 11 | 16 | Yes, 34 ops; HTTP listener forwards to instance targets |
| Secrets Manager | 6 | 16 | Yes, 23 |
| Route 53 | 9 | 14 | Yes, 27 ops; embedded DNS for private zones only |
| AWS Backup | 12 | 13 | Yes, 20 ops |
| EventBridge | 4 | 13 | Yes, 40 (+Scheduler 12) |
| Transit Gateway | 8 | 12 | API yes (TGW, attachments, route tables); no data path |
| **Site-to-Site VPN / CGW / VGW** | 8 | 11 | **Missing** (only `DescribeVpnGateways`, which returns empty) |
| CloudFront | 5 | 11 | Yes, 50 ops (management plane) |
| DMS | 11 | 11 | Yes, 20 ops (control plane) |
| CodePipeline/CodeDeploy/CodeCommit/CodeArtifact (CodeSuite) | 9 | 11 | Pipeline 44, Deploy 30, Artifact 30, the Code*Build* service 20; **CodeCommit not listed** |
| API Gateway | 9 | 10 | Yes, v1 80, v2 53 |
| Auto Scaling | 3 | 9 | Yes, 33 |
| CloudTrail | 4 | 9 | Yes, 14 |
| SNS / SQS | 4 / 4 | 9 / 9 | Yes, 39 / 23 |
| DataSync | 7 | 7 | Yes, 48 (control plane) |
| ElastiCache | 4 | 7 | Yes, 30, real Redis containers |
| **Direct Connect** | 5 | 6 | **Missing** |
| ECS/Fargate | 4 | 6 | Yes, 58 |
| Athena/Glue | 0 | 6 | Yes, 21 / 38 |
| CloudWatch Logs | 1 | 5 | Yes, 17 |
| **Storage Gateway** | 4 | 4 | **Missing** |
| Network Firewall | 3 | 4 | Yes, 27 (control plane) |
| EKS, ECR, Config, Beanstalk, Cognito | 1–4 | 4 each | Yes |
| Transfer Family, RDS Proxy, Budgets/CE | ≤3 | 3 | Yes |
| **X-Ray** | 1 | 3 | **Missing** |
| **Snow Family** | 2 | 2 | **Missing** |
| Global Accelerator, Organizations, STS, Control Tower, WAF, ACM, Kinesis, Step Functions, GuardDuty/Inspector/SecHub | ≤1 | ≤2 | Yes |
| **Amplify** | 1 | 1 | **Missing** |

Nine labs have no single main service: capstones, runbooks and decision-matrix labs.

### Regions

All 530 labs carry `ap-southeast-2 (Sydney)`, and the `/labs` page says "100%". A few titles mention cross-region or multi-region (SnapMirror, FSx ONTAP DR, capstone multi-region). The second region is not named in public metadata.

### Console vs CLI (inferred from the TOC only)

| Mode | Labs |
|---|---|
| Console only | 510 |
| Console + CLI in body steps | 11 |
| Console + IaC (CloudFormation/SAM/Terraform) | 4 |
| Console + CLI + IaC | 3 |
| Unspecified | 2 |

297 TOCs include a "Single-Shot Automated Cleanup Script" or Bash cleanup. The labs' verification steps are console screenshots or "Expected vs Measured" tables. Whether they contain CLI checks needs the gated body to confirm.

## Part B: Floci 2.3.0 coverage

### Source and maturity (verified)

- Repo: `github.com/floci-io/floci`, MIT licence, about 27.4k stars. Last push 2026-10-31, 177 open issues.
- Tag `2.3.0` was released 2026-10-15. The cadence is roughly every 1–3 weeks: 2.0.0 on 09-01, 2.1.0 on 09-15, 2.2.0 on 10-06.
- 2.0.0 had BREAKING changes (Step Functions JSONata). The 2.3.0 changelog lists features, fixes and performance work, with no BREAKING section.
- The old image name `hectorvent/floci` is deprecated in favour of `floci/floci`. The Java package is still `io.github.hectorvent.floci`.
- I read the docs at tag 2.3.0 (`docs/services/*.md`) and checked them against `src/main/java/.../services/*`. The live floci.io docs track `main`, so they may be ahead of 2.3.0.

### Requested services: support and key operations

| Service | Status | Key ops present | Notable gaps or caveats |
|---|---|---|---|
| EC2 | Supported | Run/Start/Stop/Reboot/Terminate, CreateFleet, Spot requests, launch templates (+versions), key pairs, AMIs (Describe/Create/Register/Copy/Deregister), ENIs, EIPs, volumes (Create/Attach/Detach/Modify), capacity reservations, dedicated hosts, IPAM, instance profiles, EBS default encryption | **No `CreateSnapshot`, `CopySnapshot`, `CreatePlacementGroup`, `CreateDhcpOptions`** (only `DescribeSnapshots`). Each instance is a Docker container; any AMI ID falls back to Amazon Linux 2023. The matrix line "78 ops" is stale; the docs list 191 actions and the source has about 194. |
| VPC (EC2 API) | Supported API | VPC/subnet/SG/SG rules, IGW, route tables + routes, NAT GW, NACL + entries, peering, prefix lists, VPC endpoints, flow logs, secondary CIDR, TGW + VPC/peering attachments + TGW route tables/propagation | **No VPN connection, customer gateway, VGW lifecycle, egress-only IGW lifecycle or Client VPN.** One Docker network per VPC. Routing, NACL, NAT and peering are **not** emulated. SGs are enforced only with `FLOCI_NETWORK_SECURITY_GROUP_ENFORCEMENT_ENABLED=true` (Linux/nftables, not rootless). Flow logs are metadata. On OrbStack, isolation between VPCs is lost. |
| RDS | Supported (98 ops) | Instances, read replicas, snapshots, PITR restore, param/option/subnet groups, proxies, event subscriptions, start/stop/reboot | Engines that run: **postgres, mysql, mariadb, sqlserver**. **Oracle is not emulated.** `MultiAZ`/`StorageType`/`Iops` are not applied on modify; all storage reports `gp2`. Option groups are metadata. |
| Aurora | Control plane | CreateDBCluster, cluster endpoints/params/snapshots, Failover, Global clusters + switchover, Serverless v2 config | Backed by a plain MySQL/PG container. Aurora storage and replica behaviour are not real. |
| S3 | Supported (58) | Buckets/objects, versioning, lifecycle, Object Lock, website, notifications, presign, tagging | **Replication is config-only** (no objects are copied). |
| IAM / STS | Supported (167 / 7) | Users, roles, policies, instance profiles, AssumeRole | **Policy enforcement is off by default**; turn it on with `enforcement-enabled`. |
| Lambda | Supported (55) | Real containers, event source mappings, URLs | — |
| DynamoDB (+Streams) | Supported (28 + 4) | Tables, GSI/LSI, streams | `/_floci/state/reset` is refused (409) in one storage mode (see doc). |
| SQS / SNS | Supported (23 / 39) | — | — |
| CloudWatch metrics | Supported (11) | Put/Get metrics, alarms, dashboards | The alarm evaluator handles **single-metric alarms only**. |
| CloudWatch Logs | Supported (17) | Groups/streams, metric and subscription filters, Insights queries | — |
| CloudFormation | Supported (36) | Stacks, change sets, StackSets, stack policy, DeletionPolicy Retain | Resource-type coverage is per service (see `cloudformation.md`). |
| ELBv2 (ALB/NLB) | Supported (34) | LB, listeners, rules, TGs, target health | HTTP listeners really forward to instance targets on host-bound ports. ELB Classic has 20 ops. |
| Auto Scaling | Supported (33) | ASG, launch configs, policies, scheduled actions, lifecycle hooks, warm pools | Application Auto Scaling has 10 ops. |
| Route 53 | Supported (27) | Hosted zones, record sets, health checks, VPC association | Embedded DNS on :53 answers **private zones only**. Resolver has 18 ops. |
| ECS / EKS / ECR | Supported (58 / 7 matrix, 33 in doc / 17) | ECS tasks, EKS on k3s, ECR on registry:2 | — |
| ElastiCache | Supported (30) | Clusters, replication groups, serverless | Real Redis behind a TCP proxy. |
| Secrets Manager / KMS | Supported (23 / 42) | — | — |
| API Gateway | Supported (v1 80 / v2 53) | Includes data plane | — |
| EventBridge / Step Functions | Supported (40 / 32) | Plus Scheduler 12, Pipes 7 | — |
| CloudFront | Supported (50 ops; management plane) | Distributions, OAC/OAI, functions, invalidations | Not a CDN data path (inferred from "management-plane"). |
| EFS | Supported (26) | File systems, mount targets, access points, policies, lifecycle | — |
| Kinesis | Supported (29) | — | — |
| Backup, DataSync, DMS, Transfer, Network Firewall, Config, CloudTrail, CodePipeline/CodeDeploy, WAFv2, ACM, Global Accelerator, Organizations, Control Tower | Supported (control plane) | See `docs/services/<svc>.md` | Mostly records and lifecycle, not data movement (inferred from op lists). |
| **FSx, Storage Gateway, Direct Connect, Snowball, X-Ray, Amplify, Shield, CodeCommit, Client VPN, S2S VPN** | **Absent** | — | No docs page and no `services/<name>` package in 2.3.0 source. |

### "List all resources" options (verified)

| Endpoint | What it returns | Limits |
|---|---|---|
| Resource Groups Tagging API (`tagging`, 5 ops: Tag/Untag/GetResources/GetTagKeys/GetTagValues) | Merges each owning service's tags with the tagging store. Supports `ResourceTypeFilters` and pagination. | **Only resources with ≥1 tag.** IAM ARNs are never listed. Results are scoped to the request region and account. Coverage is limited to services Resource Explorer indexes. |
| Resource Explorer 2 (`ListResources`, `Search`) | **Live** query of every provider's `getResources()`, with no stale index. A default index and view are created in the default region at startup. | Covers about 31 services. EC2 covers only `instance, vpc, subnet, security-group, volume, internet-gateway, natgateway, route-table`. **Not covered:** NACL, ENI, EIP, peering, TGW, VPC endpoints, flow logs, key pairs, Route 53 (stated in docs), EFS, ELB listeners/rules, Auto Scaling, CloudWatch alarms, Backup, DMS, DataSync, and others. Regions other than the default need `CreateIndex` first. `Search` stops at 1000 results. |
| `/_floci/*` | `health`, `info`, `state/reset`, `reset`, `init`, `ui`, `ca` | No documented resource-dump endpoint was found. |

For a full resource graph, per-service `Describe*`/`List*` calls are still needed for anything outside the Resource Explorer list.

### Region and multi-region caveats (verified unless marked)

- The default region is `us-east-1` (`FLOCI_DEFAULT_REGION`), which is used when a request names no region. Region is taken per request from the SigV4 scope.
- Default resources (VPC `172.31.0.0/16`, 3 subnets in AZ a/b/c, SG, IGW, RTB, NACL) are seeded for the default region at startup and for **other regions on first access**.
- `DescribeRegions` returns the 17 commercial regions that need no opt-in, and all 34 with `AllRegions=true`. ap-southeast-2 is a standard non-opt-in region, so it is accepted (inferred from the partition rules). Unknown regions get a 400 unless `FLOCI_PARTITIONS_ALLOW_UNKNOWN_REGIONS=true`.
- **Tagging API:** an ARN whose region differs from the request region fails `TagResources` with 400. Reads are per region, so a multi-region collector must call once per region.
- **Resource Explorer:** only the default region has an index out of the box.
- Cross-region features are not emulated: S3 replication is config-only, and RDS global clusters and TGW peering are control plane only.

## Trade-offs for the plan (ranked)

1. **Target the 415 api-covered labs first**, especially DVA, RDS and SOA (303 of the 415). Set `FLOCI_DEFAULT_REGION=ap-southeast-2` so lab ARNs and region text match. This is the lowest risk and is already within Floci's strengths.
2. **Treat the 73 control-plane-only labs as "build-the-topology" labs.** Grade them on resource state (route entries, NACL rules, attachments), not on connectivity tests. Most Network labs fall here. Grading on connectivity would give false passes or false fails.
3. **Exclude or mark unsupported the 34 blocked plus 8 degraded labs** (FSx, VPN/DX, Storage Gateway, Snow, X-Ray, Amplify). No Floci version has these services. Filling the gap would mean writing our own stubs, which costs a lot to maintain against Floci's 1–3 week release cadence.
4. **Build resource discovery as a hybrid.** Use Resource Explorer `ListResources` for the about 31 covered types, plus targeted `Describe*` calls for NACL, ENI, EIP, TGW, peering, endpoints, Route 53, ELB listeners and Auto Scaling. The Tagging API alone misses every untagged resource, which describes most console-created lab resources.

## Method and confidence

- **Verified:** catalog size, slugs, titles, badges, TOCs and the services/cost fields (all 530 pages). The Floci service list, op names and caveats come from the 2.3.0 tag docs plus a source package and EC2 dispatch diff.
- **Inferred:** main service, mentioned services and the console/CLI split (keyword regex over title, services field and TOC, which may miss services that appear only in the gated body). The `floci_fit` column uses a rule-based classifier on those features (missing set plus title regex for routing/NAT/NACL/peering/replication/failover). "Level/duration are template defaults" is also an inference.
- **Not covered:** gated lab bodies (exact CLI/console steps and resources created), Floci runtime testing of any lab, CloudFormation resource-type coverage per type, and Floci `main` changes after 2.3.0.

## Sources

- labaws.site: [robots.txt](https://labaws.site/robots.txt), [sitemap.xml](https://labaws.site/sitemap.xml), [/labs](https://labaws.site/labs), sample [lab-007-nat-gateway](https://labaws.site/labs/lab-007-nat-gateway), bundle `https://labaws.site/assets/index-BIvU6xBc.js` (API base `j4uexieqdg.execute-api.ap-southeast-2.amazonaws.com`, 401 without auth)
- Floci repo and releases: [github.com/floci-io/floci](https://github.com/floci-io/floci), [2.3.0 tag](https://github.com/floci-io/floci/tree/2.3.0), [CHANGELOG](https://github.com/floci-io/floci/blob/2.3.0/CHANGELOG.md)
- Floci docs at 2.3.0: [services index](https://github.com/floci-io/floci/blob/2.3.0/docs/services/index.md), [ec2](https://github.com/floci-io/floci/blob/2.3.0/docs/services/ec2.md), [rds](https://github.com/floci-io/floci/blob/2.3.0/docs/services/rds.md), [s3](https://github.com/floci-io/floci/blob/2.3.0/docs/services/s3.md), [elb](https://github.com/floci-io/floci/blob/2.3.0/docs/services/elb.md), [route53](https://github.com/floci-io/floci/blob/2.3.0/docs/services/route53.md), [cloudwatch](https://github.com/floci-io/floci/blob/2.3.0/docs/services/cloudwatch.md), [iam](https://github.com/floci-io/floci/blob/2.3.0/docs/services/iam.md), [resource-groups-tagging](https://github.com/floci-io/floci/blob/2.3.0/docs/services/resource-groups-tagging.md), [resource-explorer](https://github.com/floci-io/floci/blob/2.3.0/docs/services/resource-explorer.md), [environment-variables](https://github.com/floci-io/floci/blob/2.3.0/docs/configuration/environment-variables.md), [partitions](https://github.com/floci-io/floci/blob/2.3.0/docs/configuration/partitions.md)
- EC2 dispatch source: [Ec2QueryHandler.java](https://github.com/floci-io/floci/blob/2.3.0/src/main/java/io/github/hectorvent/floci/services/ec2/Ec2QueryHandler.java)
- Live docs (track main): [floci.io/floci/services/](https://floci.io/floci/services/)

## Unresolved questions

1. Do the gated lab bodies include CLI verification commands we could reuse as checks, or only console screenshots? This needs a logged-in sample of about 5 labs.
2. Which second region do the cross-region labs use (FSx ONTAP DR, Network capstone)?
3. Should blocked labs be hidden, or shown as "read-only theory" in our platform? This is a product decision.
4. Is the host Linux (needed for SG enforcement through nftables) or macOS Docker Desktop/OrbStack (no SG enforcement, and VPC isolation lost on OrbStack)?
