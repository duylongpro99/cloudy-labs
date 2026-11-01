"""ECR, ECS, EKS, Elastic Beanstalk, CodeBuild, CodeDeploy, CodePipeline and CodeArtifact kinds: where
their nodes sit, how a pipeline links to its source, build and deploy targets, that no secret value
(build variables, Beanstalk option values, action configuration, cluster CA data) reaches a prop, and
the commands their builder ops run."""
import json
from datetime import datetime, timezone

from cloudy_labs.builder.catalog import op_named, prepare
from cloudy_labs.graph.collector import CollectContext, build_graph
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.registry import default_registry

REGION = "ap-southeast-2"
ACCOUNT = "000000000000"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/delivery"
BUCKET = "delivery-artifacts"
VPC = "vpc-0a1b2c3d"
SG = "sg-0a1b2c3d"
EKS = f"arn:aws:eks:{REGION}:{ACCOUNT}:cluster/web-cluster"
APP = f"arn:aws:elasticbeanstalk:{REGION}:{ACCOUNT}:application/web"
ENV = f"arn:aws:elasticbeanstalk:{REGION}:{ACCOUNT}:environment/web/web-dev"
PROJECT = f"arn:aws:codebuild:{REGION}:{ACCOUNT}:project/web-build"
DEPLOY_APP = "0f1e2d3c-0000-4000-8000-000000000001"
PIPELINE = f"arn:aws:codepipeline:{REGION}:{ACCOUNT}:web-pipeline"
DOMAIN = f"arn:aws:codeartifact:{REGION}:{ACCOUNT}:domain/acme"
LIBS = f"arn:aws:codeartifact:{REGION}:{ACCOUNT}:repository/acme/libs"
STORE = f"arn:aws:codeartifact:{REGION}:{ACCOUNT}:repository/acme/npm-store"
SECRET_VALUE = "do-not-read-this-value"
KINDS = {"ecr-repository", "ecs-cluster", "eks-cluster", "beanstalk-application", "beanstalk-environment", "codebuild-project",
         "codedeploy-application", "codepipeline-pipeline", "codeartifact-domain", "codeartifact-repository"}
PLATFORM = f"arn:aws:elasticbeanstalk:{REGION}::platform/Docker running on 64bit Amazon Linux 2023/4.3.0"
CA_DATA = "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t"


def action(category: str, provider: str, configuration: dict) -> dict:
    return {"name": provider, "actionTypeId": {"category": category, "owner": "AWS", "provider": provider, "version": "1"},
            "configuration": configuration}


def raw() -> dict[str, list[dict]]:
    """Items as the collector holds them after listing and enrichment, from Floci's answers."""
    return {
        "vpc": [{"VpcId": VPC, "CidrBlock": "10.0.0.0/16"}],
        "security-group": [{"GroupId": SG, "GroupName": "eks", "VpcId": VPC}],
        "iam-role": [{"RoleName": "delivery", "Arn": ROLE}],
        "s3-bucket": [{"Name": BUCKET}],
        "ecr-repository": [{
            "repositoryName": "web-images", "repositoryArn": f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/web-images",
            "repositoryUri": f"{ACCOUNT}.dkr.ecr.{REGION}.localhost:4567/web-images", "imageTagMutability": "MUTABLE",
            "imageScanningConfiguration": {"scanOnPush": True}, "encryptionConfiguration": {"encryptionType": "AES256"},
            "_Images": [{"imageDigest": "sha256:1", "imageTag": "v2"}, {"imageDigest": "sha256:2", "imageTag": "v1"},
                        {"imageDigest": "sha256:3"}]}],
        "eks-cluster": [{"name": "web-cluster", "_Cluster": {
            "arn": EKS, "name": "web-cluster", "status": "ACTIVE", "version": "1.29", "roleArn": ROLE,
            "endpoint": "https://localhost:6500", "certificateAuthority": {"data": CA_DATA},
            "resourcesVpcConfig": {"vpcId": VPC, "subnetIds": ["subnet-2", "subnet-1"], "securityGroupIds": [SG],
                                   "endpointPublicAccess": True}}}],
        "beanstalk-application": [{"ApplicationName": "web", "ApplicationArn": APP, "ConfigurationTemplates": ["default"]}],
        "beanstalk-environment": [{
            "EnvironmentName": "web-dev", "EnvironmentArn": ENV, "EnvironmentId": "e-abc", "ApplicationName": "web",
            "Status": "Ready", "Health": "Green", "Tier": {"Name": "WebServer"}, "_AppArn": APP,
            "_DeploymentPolicy": "Immutable"}],
        "codebuild-project": [{"name": "web-build", "_Project": {
            "arn": PROJECT, "name": "web-build", "serviceRole": ROLE,
            "source": {"type": "CODEPIPELINE", "buildspec": f"phases: {{build: {{commands: [echo {SECRET_VALUE}]}}}}"},
            "artifacts": {"type": "S3", "location": BUCKET},
            "environment": {"type": "LINUX_CONTAINER", "image": "aws/codebuild/standard:7.0", "computeType": "BUILD_GENERAL1_SMALL",
                            "environmentVariables": [{"name": "DB_PASSWORD", "value": SECRET_VALUE, "type": "PLAINTEXT"},
                                                     {"name": "DB_HOST", "value": "/app/db-host", "type": "PARAMETER_STORE"}]}}}],
        "codedeploy-application": [{"applicationName": "web-deploy", "_Groups": ["prod", "dev"],
                                    "_App": {"applicationId": DEPLOY_APP, "computePlatform": "Lambda"}}],
        "codepipeline-pipeline": [{"name": "web-pipeline", "version": 3, "pipelineType": "V1", "_Pipeline": {
            "metadata": {"pipelineArn": PIPELINE},
            "pipeline": {"name": "web-pipeline", "roleArn": ROLE, "artifactStore": {"type": "S3", "location": BUCKET}, "stages": [
                {"name": "Source", "actions": [action("Source", "S3", {"S3Bucket": BUCKET, "S3ObjectKey": "src.zip"})]},
                {"name": "Build", "actions": [action("Build", "CodeBuild", {"ProjectName": "web-build"})]},
                {"name": "Deploy", "actions": [action("Deploy", "ElasticBeanstalk", {"ApplicationName": "web", "EnvironmentName": "web-dev"}),
                                               action("Deploy", "CodeDeploy", {"ApplicationName": "web-deploy", "OAuthToken": SECRET_VALUE})]},
            ]}}}],
        "codeartifact-domain": [{"name": "acme", "arn": DOMAIN, "status": "Active", "_Domain": {"repositoryCount": 2}}],
        "codeartifact-repository": [
            {"name": "libs", "arn": LIBS, "domainName": "acme", "_DomainArn": DOMAIN,
             "_Repo": {"upstreams": [{"repositoryName": "npm-store"}], "externalConnections": []}},
            {"name": "npm-store", "arn": STORE, "domainName": "acme", "_DomainArn": DOMAIN,
             "_Repo": {"upstreams": [], "externalConnections": [{"externalConnectionName": "public:npmjs"}]}},
        ],
    }


def graph() -> ResourceGraph:
    ctx = CollectContext(clients=lambda s: None, now=datetime(2026, 1, 1, tzinfo=timezone.utc), ports=lambda: {}, region=REGION)
    return build_graph(default_registry(), raw(), ctx, regions=[REGION], account=ACCOUNT)


def test_children_sit_in_their_application_domain_and_vpc():
    g = graph()
    parents = {c.child: c.parent for c in g.contains}
    assert parents[ENV] == APP
    assert parents[LIBS] == DOMAIN and parents[STORE] == DOMAIN
    assert parents[EKS] == VPC
    assert parents[PIPELINE] == REGION and parents[PROJECT] == REGION


def test_props_summarise_images_variables_and_stages():
    nodes = {n.id: n for n in graph().nodes}
    repo = nodes[f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/web-images"]
    assert repo.props["images"] == 3 and repo.props["imageTags"] == ["v1", "v2"] and repo.props["scanOnPush"] is True
    assert nodes[EKS].props["subnets"] == ["subnet-1", "subnet-2"]
    assert nodes[PROJECT].props["variableNames"] == ["DB_PASSWORD:PLAINTEXT", "DB_HOST:PARAMETER_STORE"]
    assert nodes[ENV].props["deploymentPolicy"] == "Immutable"
    assert nodes[DEPLOY_APP].label == "web-deploy" and nodes[DEPLOY_APP].props["deploymentGroups"] == ["dev", "prod"]
    assert nodes[PIPELINE].props["actions"] == ["Source:S3", "Build:CodeBuild", "Deploy:ElasticBeanstalk", "Deploy:CodeDeploy"]
    assert nodes[STORE].props["externalConnections"] == ["public:npmjs"]


def test_a_pipeline_links_its_source_build_and_deploy_targets():
    edges = {(e.kind, e.from_, e.to) for e in graph().edges}
    s3 = f"arn:aws:s3:::{BUCKET}"
    assert ("pipeline-source", s3, PIPELINE) in edges
    assert ("upload-to", PIPELINE, s3) in edges and ("upload-to", PROJECT, s3) in edges
    assert ("pipeline-action", PIPELINE, PROJECT) in edges
    assert ("pipeline-action", PIPELINE, ENV) in edges
    assert ("pipeline-action", PIPELINE, DEPLOY_APP) in edges
    assert {("execution-role", PIPELINE, ROLE), ("execution-role", PROJECT, ROLE), ("execution-role", EKS, ROLE)} <= edges
    assert ("attached", SG, EKS) in edges
    assert ("upstream", LIBS, STORE) in edges


def test_no_secret_value_reaches_a_prop():
    g = graph()
    text = json.dumps([n.props for n in g.nodes if n.kind in KINDS], default=str)
    assert SECRET_VALUE not in text and CA_DATA not in text and "/app/db-host" not in text


def test_beanstalk_reads_only_the_deployment_policy_option():
    rt = default_registry().by_kind["beanstalk-environment"]
    settings = next(e for e in rt.enrich if e.method == "describe_configuration_settings")
    assert "aws:elasticbeanstalk:command" in settings.pick and "DeploymentPolicy" in settings.pick
    assert ("Status", ["Terminated", "Terminating"]) in [(f.path, f.not_in) for f in rt.filter]


def test_codedeploy_ops_run_the_cli_deploy_command():
    prepared = prepare(op_named("create-codedeploy-application"), {"applicationName": "web-deploy"},
                       graph=graph(), azs=[], choices={}, tags={})
    assert prepared.problems == []
    assert prepared.argv[1:3] == ["deploy", "create-application"]
    assert "--compute-platform" in prepared.argv


def test_a_beanstalk_environment_takes_its_platform_by_arn():
    prepared = prepare(op_named("create-beanstalk-environment"),
                       {"ApplicationName": "web", "EnvironmentName": "web-prod", "PlatformArn": PLATFORM},
                       graph=graph(), azs=[], choices={}, tags={})
    assert prepared.problems == []
    assert prepared.argv[prepared.argv.index("--platform-arn") + 1] == PLATFORM


def test_delete_ops_find_their_node_by_name():
    g = graph()
    for op, params, node in [
        ("delete-codepipeline-pipeline", {"name": "web-pipeline"}, PIPELINE),
        ("delete-codebuild-project", {"name": "web-build"}, PROJECT),
        ("delete-codedeploy-application", {"applicationName": "web-deploy"}, DEPLOY_APP),
        ("delete-eks-cluster", {"name": "web-cluster"}, EKS),
        ("terminate-beanstalk-environment", {"EnvironmentName": "web-dev"}, ENV),
    ]:
        prepared = prepare(op_named(op), params, graph=g, azs=[], choices={}, tags={})
        assert prepared.problems == [] and prepared.target == node, op



def test_a_container_is_found_by_its_kind_when_another_node_shares_its_name():
    g = graph()
    app = next(n for n in g.nodes if n.id == APP)
    namesake = app.model_copy(update={"id": f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/web", "kind": "ecr-repository"})
    g = g.model_copy(update={"nodes": [namesake, *g.nodes]})
    prepared = prepare(op_named("create-beanstalk-environment"),
                       {"ApplicationName": "web", "EnvironmentName": "web-prod", "PlatformArn": PLATFORM}, graph=g, azs=[], choices={}, tags={})
    assert prepared.problems == []
