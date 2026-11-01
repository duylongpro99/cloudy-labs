# Wave 3: delivery group (ECR, ECS, EKS, Elastic Beanstalk, CodeBuild, CodeDeploy, CodePipeline, CodeArtifact)

Status: DONE_WITH_CONCERNS. The group has ten new kinds in eight YAML files and one test file. All ten contracts passed against live Floci 2.3.0, a live collect gave no warnings, and every probe resource has been deleted. No existing file was edited.

## Files created

- `server/src/cloudy_labs/registry/ecr.yaml`
- `server/src/cloudy_labs/registry/ecs.yaml`
- `server/src/cloudy_labs/registry/eks.yaml`
- `server/src/cloudy_labs/registry/elasticbeanstalk.yaml`
- `server/src/cloudy_labs/registry/codebuild.yaml`
- `server/src/cloudy_labs/registry/codedeploy.yaml`
- `server/src/cloudy_labs/registry/codepipeline.yaml`
- `server/src/cloudy_labs/registry/codeartifact.yaml`
- `server/tests/test_registry_delivery.py` (8 tests)

## Kinds

| kind | service | parent | edges | ops | contract | caveats / floci |
|---|---|---|---|---|---|---|
| ecr-repository | ecr | region | encrypted-by kms-key/kms-alias | create-ecr-repository, put-image-scanning-configuration, delete-ecr-repository | create, scan config, delete | `ecr-no-scan` (StartImageScan/DescribeImageScanFindings refused) |
| ecs-cluster | ecs | region | none | create-ecs-cluster, update-ecs-cluster-settings, delete-ecs-cluster | create, settings, delete | none |
| eks-cluster | eks | vpc (`resourcesVpcConfig.vpcId`), else region | execution-role to iam-role; attached from security-group (reverse) | create-eks-cluster, delete-eks-cluster | needs role; create, delete | `eks-no-cluster-update` (UpdateClusterConfig refused) |
| beanstalk-application | elasticbeanstalk | region | none | create-, update-, delete-beanstalk-application | create, description, delete | floci control-plane-only |
| beanstalk-environment | elasticbeanstalk | beanstalk-application (`_AppArn`), else region | none | create-, update-, terminate-beanstalk-environment | needs app; create, update, terminate; parent app | `beanstalk-platform-not-checked`; floci control-plane-only |
| codebuild-project | codebuild | region | execution-role; upload-to s3-bucket; encrypted-by; attached security-group | create-, update-, delete-codebuild-project | needs role; create (NO_SOURCE), timeout 15, delete | none |
| codedeploy-application | codedeploy | region | none | create-, rename-, delete-codedeploy-application | create, rename, delete | none |
| codepipeline-pipeline | codepipeline | region | execution-role; upload-to s3-bucket; pipeline-source from s3-bucket/ecr-repository (reverse); pipeline-action to codebuild-project, codedeploy-application, beanstalk-environment, lambda-function | create-, update-, delete-codepipeline-pipeline | needs role and bucket; create, update stages, delete | none |
| codeartifact-domain | codeartifact | region | encrypted-by kms-key/kms-alias | create-, put-codeartifact-domain-policy, delete- | create, policy, delete | none |
| codeartifact-repository | codeartifact | codeartifact-domain (`_DomainArn`), else region | upstream to codeartifact-repository | create-, update-, delete-codeartifact-repository | needs domain and upstream; create, set upstreams, delete; parent domain | none |

View orders used: 600 (ecr), 605 (ecs), 610 (eks), 615 and 616 (beanstalk), 620 (codebuild), 625 (codedeploy), 630 (codepipeline), 635 and 636 (codeartifact). All are unique and inside 600-649. Every icon is a real file under `aws-icon-pkg/`. The heaviest is the Beanstalk Application resource icon at 1892 triangles, which is under the 2000 budget.

Secrets are kept out of props in these places:

- CodeBuild exposes only `name:type` of its environment variables, never their values or the buildspec.
- Beanstalk reads only the `aws:elasticbeanstalk:command` DeploymentPolicy option.
- CodePipeline reads action configuration only for the names its edges need.
- EKS never reads the certificate authority data.
- Props that matched the chat deny-list were renamed: `envId`, `containerType` and `variableNames`.

The coverage did not name an ECS service, an ECS task definition, a CodeDeploy deployment group or an EKS node group, so I did not add those kinds.

## make_delivery(c)

Note: the EKS line starts a real k3s container on Floci. It is removed when the cluster is deleted, which takes about 3 seconds. The ECR line starts a `registry:2` container that lives until the last repository is deleted. Drop either line if the scene must not run containers.

```python
def make_delivery(c):
    """One of every delivery kind: an ECR repository, an ECS cluster, an EKS cluster (Floci starts a
    k3s container for it), a Beanstalk application with an environment, a CodeBuild project, a
    CodeDeploy application, a pipeline S3 source -> CodeBuild -> Beanstalk, and a CodeArtifact domain
    holding a repository with an upstream."""
    p = "w3-"
    region = c["s3"].meta.region_name
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {
        "Service": ["codebuild.amazonaws.com", "codepipeline.amazonaws.com", "eks.amazonaws.com"]}}]}
    role = c["iam"].create_role(RoleName=f"{p}delivery-role", AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
    bucket = f"{p}delivery-artifacts"
    c["s3"].create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})

    c["ecr"].create_repository(repositoryName=f"{p}delivery-app", imageScanningConfiguration={"scanOnPush": True})
    c["ecs"].create_cluster(clusterName=f"{p}delivery", settings=[{"name": "containerInsights", "value": "enabled"}])
    c["eks"].create_cluster(name=f"{p}delivery", roleArn=role, resourcesVpcConfig={"endpointPublicAccess": True})

    eb = c["elasticbeanstalk"]
    eb.create_application(ApplicationName=f"{p}delivery-web", Description="dummy web app")
    eb.create_environment(ApplicationName=f"{p}delivery-web", EnvironmentName=f"{p}delivery-web-dev",
                          SolutionStackName="64bit Amazon Linux 2023 v4.3.0 running Docker",
                          OptionSettings=[{"Namespace": "aws:elasticbeanstalk:command", "OptionName": "DeploymentPolicy",
                                           "Value": "Rolling"}])

    c["codebuild"].create_project(
        name=f"{p}delivery-build", serviceRole=role, source={"type": "CODEPIPELINE"},
        artifacts={"type": "CODEPIPELINE"},
        environment={"type": "LINUX_CONTAINER", "image": "aws/codebuild/standard:7.0", "computeType": "BUILD_GENERAL1_SMALL",
                     "environmentVariables": [{"name": "STAGE", "value": "dev", "type": "PLAINTEXT"}]})
    c["codedeploy"].create_application(applicationName=f"{p}delivery-deploy", computePlatform="Server")

    c["codepipeline"].create_pipeline(pipeline={
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

    ca = c["codeartifact"]
    ca.create_domain(domain=f"{p}delivery")
    ca.create_repository(domain=f"{p}delivery", repository=f"{p}delivery-npm-store")
    ca.associate_external_connection(domain=f"{p}delivery", repository=f"{p}delivery-npm-store", externalConnection="public:npmjs")
    ca.create_repository(domain=f"{p}delivery", repository=f"{p}delivery-libs", upstreams=[{"repositoryName": f"{p}delivery-npm-store"}])
```

Clients needed: iam, s3, ecr, ecs, eks, elasticbeanstalk, codebuild, codedeploy, codepipeline and codeartifact. The function needs `import json`. I ran it live with a `pb-delivery-mk-` prefix: it worked, the collect showed the expected parents and edges, and the resources were then deleted.

## Missing APIs (no YAML)

- **CodeCommit:** Floci has no CodeCommit service. Labs lab-129, lab-25, lab-46 and lab-83 stay blocked.
- **ECR:** StartImageScan and DescribeImageScanFindings are refused. This is covered by the `ecr-no-scan` caveat.
- **EKS:** UpdateClusterConfig, UpdateClusterVersion, UpdateNodegroupConfig and UpdateNodegroupVersion are not in floci-ops. UpdateClusterConfig is refused live and is covered by the `eks-no-cluster-update` caveat.
- **ECR lifecycle policy:** PutLifecyclePolicy and GetLifecyclePolicy work live but are missing from `floci-ops-2.3.0.json`, so I added no op. Suggestion: add them to floci-ops, then add a lifecycle-policy op on ecr-repository and a catalog override for lab-97 (lifecycle policy).

## Floci 2.3.0 quirks (verified live)

- **ECR:** the first repository starts a real `registry:2` container, and deleting the last repository removes it.
- **EKS:** each cluster starts a real k3s container. It is ACTIVE after about 20 s at endpoint `https://localhost:6500` with version 1.29, and deletion takes about 3 s. EKS is therefore not control-plane-only, so it has no `floci` control-plane-only mark.
- **ECS:** a cluster alone runs nothing, but tasks would run real Docker containers.
- **Elastic Beanstalk:** control-plane-only. Environments are Ready/Green at once with a `*.elasticbeanstalk.local` CNAME, and nothing serves on it. Any PlatformArn is accepted, but SolutionStackName reads back as the Docker stack.
- **CodeBuild:** StartBuild runs real Docker. No op starts a build.
- **CodeDeploy:** there is no application ARN, so the node id is the applicationId.
- **CodePipeline:** new pipelines are pipelineType V1 with executionMode SUPERSEDED.
- **CodeArtifact:** the domain encryption key is reported as `alias/aws/codeartifact`.

## Changes needed in files I do not own

1. **`builder/shapes.py` CLI_SERVICE:** codedeploy must map to `deploy`. The coordinator already did this, and `test_codedeploy_ops_run_the_cli_deploy_command` covers it.
2. **`builder/sanitize.py`:** fields ending in Name must match `[A-Za-z0-9._-]{1,64}`, so Beanstalk `SolutionStackName` (which has spaces) is refused. The create op uses PlatformArn instead. An exemption for (elasticbeanstalk, SolutionStackName) would let the builder offer solution stacks, which is what most labs use.
3. **`builder/catalog.py` `_scene_problems`:** the container-by-label lookup takes the first node with that label of any kind. A Beanstalk environment whose ApplicationName is "web" fails when an ECR repo or EKS cluster is also named "web". The lookup should filter by the op's container kinds.
4. **Lab tags on lowercase key/value services:** ECS, CodeBuild, CodeArtifact and CodePipeline take tags as lowercase `key`/`value`, so the builder's lab tags are not applied to them. Beanstalk has no TagResource in floci-ops.
5. **Golden files:** the `registry.json` export and the `test_app` registry golden must be regenerated, and the coverage matrix in `test_coverage` must be updated. These are the two expected failures.

## Coverage

Before, 27 labs had reasons naming these services: 23 were gaps for "the registry has no kind of ecr/ecs/eks/elasticbeanstalk/codepipeline", and 4 were blocked by CodeCommit. lab-44 (X-Ray sidecar) was also blocked by X-Ray.

After, no lab has a delivery gap. All former gap labs are now ready-with-caveats, including lab-004, lab-045, lab-080, lab-025 (EFS access point), lab-95 to lab-99, lab-02, lab-102, lab-12, lab-33, lab-40, lab-42, lab-58, lab-69, lab-78, lab-84, lab-85, lab-93 and lab-96. The remaining blocks are not caused by these services:

- lab-129, lab-25, lab-46 and lab-83 are blocked because Floci has no CodeCommit.
- lab-44 is blocked because Floci has no X-Ray.

## Tests

- `tests/test_registry_delivery.py`: 8 passed.
- Full suite at last run: 767 passed and 9 failed. None of the failures come from this group:
  - Two are expected golden failures: the `test_app` registry golden and the `test_coverage` matrix.
  - The wave1 and wave2 replay tests fail because another group's RDS kind calls `describe_event_subscriptions`, which is not in the recordings.
  - `test_runner` has a timeout that passes when run alone.
- Live checks:
  - All 10 contracts passed, with each step taking 0.2 to 0.6 s.
  - The live collect gave 0 warnings.
  - After cleanup, no `pb-delivery` or `ct-` resources remain in these services, IAM or S3, and no k3s or registry container is running.

Status: DONE_WITH_CONCERNS
Summary: Ten delivery kinds are in place with live-verified contracts, and every delivery coverage gap is closed; the only labs left blocked need CodeCommit or X-Ray, which Floci lacks.
Concerns/Blockers: Other files need changes: a sanitize exemption for SolutionStackName, a container-kind filter in catalog.py, regenerated goldens, and floci-ops entries for the ECR lifecycle APIs. EKS and ECR start real containers when used.
