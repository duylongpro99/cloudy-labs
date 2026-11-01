import json

from cloudy_labs.builder import shapes
from cloudy_labs.registry import OpField, OpSpec


def spec(api, *fields, **kw):
    return OpSpec(id="op", api=api, gesture=kw.pop("gesture", "create"), title="t", fields=list(fields), **kw)


def tail(argv):
    assert argv[-4:] == ["--profile", "lab", "--output", "json"]
    return argv[:-4]


def flags(tokens):
    out, flag = {}, None
    for t in tokens:
        if t.startswith("--"):
            flag = t
            out[flag] = []
        else:
            out[flag].append(t)
    return out


def test_fields_come_from_the_shape():
    s = spec("CreateDBInstance", "DBInstanceIdentifier", "Engine", "DBInstanceClass", "AllocatedStorage", "MultiAZ",
             "VpcSecurityGroupIds", OpField(name="DBSubnetGroupName", ref="rds-db-subnet-group", ref_by="label"))
    by = {f.name: f for f in shapes.fields(s, "rds")}
    assert by["DBInstanceIdentifier"].required and by["Engine"].required and not by["MultiAZ"].required
    assert (by["AllocatedStorage"].type, by["MultiAZ"].type, by["VpcSecurityGroupIds"].type) == ("integer", "boolean", "list")
    assert by["DBSubnetGroupName"].ref == "rds-db-subnet-group" and by["DBSubnetGroupName"].ref_by == "label"
    assert "<" not in by["Engine"].doc and by["Engine"].doc
    advanced = [f for f in by.values() if f.advanced]
    assert advanced and not {"Tags", "DBInstanceIdentifier"} & {f.name for f in advanced}
    assert by["MultiAZ"].describe()["type"] == "boolean"


def test_enums_become_choices():
    s = spec("CreateFunction", "FunctionName", "Runtime")
    runtime = next(f for f in shapes.fields(s, "lambda") if f.name == "Runtime")
    assert runtime.type == "enum" and "python3.12" in runtime.choices


def test_create_db_instance():
    s = spec("CreateDBInstance", "DBInstanceIdentifier", "Engine", "DBInstanceClass", "AllocatedStorage", "MultiAZ",
             "VpcSecurityGroupIds", defaults={"Engine": "mysql", "DBInstanceClass": "db.t3.micro", "AllocatedStorage": 20})
    params, problems = shapes.request(s, "rds", {"DBInstanceIdentifier": "lab-db", "MultiAZ": "false",
                                                 "VpcSecurityGroupIds": "sg-1, sg-2", "AllocatedStorage": ""})
    assert problems == {}
    assert params == {"DBInstanceIdentifier": "lab-db", "Engine": "mysql", "DBInstanceClass": "db.t3.micro",
                      "AllocatedStorage": 20, "MultiAZ": False, "VpcSecurityGroupIds": ["sg-1", "sg-2"]}
    assert shapes.shape_problems("rds", "CreateDBInstance", params) == []
    argv = tail(shapes.argv(s, "rds", params, {}))
    assert argv[:3] == ["aws", "rds", "create-db-instance"] and flags(argv[3:]) == {
        "--db-instance-identifier": ["lab-db"], "--db-instance-class": ["db.t3.micro"], "--engine": ["mysql"],
        "--allocated-storage": ["20"], "--vpc-security-group-ids": ["sg-1", "sg-2"], "--no-multi-az": []}


def test_unreadable_values_are_problems_per_field():
    s = spec("CreateDBInstance", "DBInstanceIdentifier", "Engine", "DBInstanceClass", "AllocatedStorage", "MultiAZ")
    _, problems = shapes.request(s, "rds", {"AllocatedStorage": "twenty", "MultiAZ": "yes"})
    assert set(problems) == {"AllocatedStorage", "MultiAZ"}
    missing = shapes.shape_problems("rds", "CreateDBInstance", {"DBInstanceIdentifier": "x"})
    assert any('"Engine"' in line for line in missing)


def test_create_function_sends_the_sample_zip():
    s = spec("CreateFunction", "FunctionName", "Runtime", "Role", "Handler",
             OpField(name="Code.ZipFile", flag="--zip-file", sample="hello-python"))
    params, problems = shapes.request(s, "lambda", {"FunctionName": "hello", "Runtime": "python3.12",
                                                    "Role": "arn:aws:iam::000000000000:role/lab", "Handler": "lambda_function.handler",
                                                    "Code.ZipFile": "file:///etc/passwd"})
    assert problems == {} and params["Code"] == {"ZipFile": "hello-python"}  # the server's sample, not the text
    argv = tail(shapes.argv(s, "lambda", params, {"Code.ZipFile": "/home/u/.cloudy-labs/samples/hello-python.zip"}))
    assert argv[:3] == ["aws", "lambda", "create-function"]
    assert argv[argv.index("--zip-file") + 1] == "fileb:///home/u/.cloudy-labs/samples/hello-python.zip"
    assert "--code" not in argv and "/etc/passwd" not in " ".join(argv)


def test_put_bucket_policy_sends_json_text():
    policy = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject",
                                                      "Resource": "arn:aws:s3:::lab-site/*"}]}
    s = spec("PutBucketPolicy", "Bucket", "Policy", gesture="attribute")
    params, problems = shapes.request(s, "s3", {"Bucket": "lab-site", "Policy": json.dumps(policy)})
    assert problems == {} and shapes.shape_problems("s3", "PutBucketPolicy", params) == []
    argv = tail(shapes.argv(s, "s3", params, {}))
    assert argv[:3] == ["aws", "s3api", "put-bucket-policy"]
    assert json.loads(argv[argv.index("--policy") + 1]) == policy


def test_list_of_structures_is_json_never_shorthand():
    s = spec("AuthorizeSecurityGroupIngress", "GroupId", "IpPermissions", gesture="modify")
    rules = [{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]
    params, problems = shapes.request(s, "ec2", {"GroupId": "sg-1", "IpPermissions": json.dumps(rules)})
    assert problems == {} and shapes.shape_problems("ec2", "AuthorizeSecurityGroupIngress", params) == []
    argv = tail(shapes.argv(s, "ec2", params, {}))
    value = argv[argv.index("--ip-permissions") + 1]
    assert json.loads(value) == rules and "IpProtocol=" not in value


def test_bad_json_is_a_problem_of_its_field():
    s = spec("AuthorizeSecurityGroupIngress", "GroupId", "IpPermissions", gesture="modify")
    _, problems = shapes.request(s, "ec2", {"GroupId": "sg-1", "IpPermissions": "[{"})
    assert "not valid JSON" in problems["IpPermissions"]


def test_an_idempotency_token_is_left_to_the_cli():
    from cloudy_labs.builder import shapes

    assert shapes.shape_problems("efs", "CreateAccessPoint", {"FileSystemId": "fs-1"}) == []
    assert shapes.shape_problems("secretsmanager", "CreateSecret", {"Name": "s"}) == []
