import pytest

from cloudy_labs.builder.sanitize import sanitize


@pytest.mark.parametrize("value", [
    "file:///etc/passwd",
    "fileb://~/.ssh/id_rsa",
    "FILE://x",
    "  fileb://x",
    "\tfile://x",
])
def test_file_prefixes_are_refused_in_text(value):
    [problem] = sanitize({"Description": value})
    assert problem.field == "Description" and "file://" in problem.message


def test_file_prefixes_are_refused_in_lists_and_deep_json():
    params = {
        "SecurityGroupIds": ["sg-1", "file://x"],
        "IpPermissions": [{"IpRanges": [{"CidrIp": "10.0.0.0/8", "Description": "FileB://y"}]}],
        "Attributes": {"Policy": {"Statement": [{"Resource": " file://z"}]}},
        "Keyed": {"file://k": "v"},
    }
    assert {p.field for p in sanitize(params)} == set(params)


def test_list_elements_may_not_start_with_a_dash():
    [problem] = sanitize({"SecurityGroupIds": ["sg-1", "--endpoint-url"]})
    assert problem.field == "SecurityGroupIds" and "'-'" in problem.message


def test_list_text_is_split_before_the_dash_check():
    assert sanitize({"SubnetIds": "subnet-1, --endpoint-url=http://evil"}, list_fields=frozenset({"SubnetIds"}))
    assert sanitize({"SubnetIds": "subnet-1 subnet-2"}, list_fields=frozenset({"SubnetIds"})) == []
    assert sanitize({"Description": "-dash is fine in text"}) == []  # a single value is one argv token


@pytest.mark.parametrize("value", ['["file:///etc/hosts"]', '[ "subnet-1", "fileb://x" ]', '["--endpoint-url", "http://evil"]',
                                   '["subnet-1","-x"]'])
def test_a_list_sent_as_json_text_is_checked_element_by_element(value):
    # The form sends a list as text, parsed into separate CLI tokens only after this check.
    [problem] = sanitize({"SubnetIds": value}, list_fields=frozenset({"SubnetIds"}))
    assert problem.field == "SubnetIds"


def test_structures_sent_as_json_text_are_checked_at_every_depth():
    assert sanitize({"Attributes": '{"Policy": {"Statement": [{"Resource": "file://z"}]}}'})
    assert sanitize({"Tags": '[{"Key": "k", "Value": "fileb://v"}]'})
    # The text stays one CLI argument: a dash inside it is a value, not an option.
    assert sanitize({"ContainerDefinitions": '[{"command": ["--port", "80"]}]'}) == []
    assert sanitize({"SubnetIds": '["subnet-1", "subnet-2"]'}, list_fields=frozenset({"SubnetIds"})) == []
    assert sanitize({"Description": "[not json, file://x"}) == []  # plain text that only starts with a bracket


@pytest.mark.parametrize("field", ["DBInstanceIdentifier", "FunctionName", "QueueName", "name"])
def test_names_keep_to_the_allowlist(field):
    assert sanitize({field: "lab-01_db.v2"}) == []
    [problem] = sanitize({field: "bad name; rm -rf"})
    assert problem.field == field and "Name tag" in problem.message
    assert sanitize({field: "x" * 65}) and sanitize({field: "ok\n"})


def test_descriptions_keep_to_the_allowlist():
    assert sanitize({"Description": "Web tier (port 80) #1"}) == []
    assert sanitize({"GroupDescription": "Mô tả có dấu"}) and sanitize({"description": "x" * 256})


def test_one_problem_per_field():
    assert len(sanitize({"Ids": ["file://a", "--b", "fileb://c"]})) == 1


@pytest.mark.parametrize("value", ["/aws/lambda/my-fn", "app#1", "ct-app-logs"])
def test_log_group_names_may_be_paths(value):
    assert sanitize({"logGroupName": value}, service="logs") == []


@pytest.mark.parametrize("value", ["has space", "x" * 513, "a\nb"])
def test_log_group_names_still_refuse_other_characters(value):
    assert [p.field for p in sanitize({"logGroupName": value}, service="logs")] == ["logGroupName"]


@pytest.mark.parametrize(("service", "field", "value"), [
    ("ssm", "Name", "/app/db-host"), ("kms", "AliasName", "alias/app-key"), ("secretsmanager", "Name", "app/db-password"),
])
def test_path_names_are_allowed_where_the_service_uses_them(service, field, value):
    assert sanitize({field: value}, service=service) == []
    assert [p.field for p in sanitize({field: value}, service="ec2")] == [field]  # elsewhere a Name stays short


def test_a_kms_alias_must_start_with_alias():
    assert [p.field for p in sanitize({"AliasName": "app-key"}, service="kms")] == ["AliasName"]


def test_other_name_fields_keep_the_short_rule():
    assert [p.field for p in sanitize({"GroupName": "/aws/x"})] == ["GroupName"]


@pytest.mark.parametrize(("service", "field", "value"), [
    ("elasticbeanstalk", "SolutionStackName", "64bit Amazon Linux 2023 v4.3.0 running Docker"),
    ("elasticbeanstalk", "SolutionStackName", "64bit Amazon Linux 2 v3.5.0 running Python 3.8"),
    ("acm", "DomainName", "*.example.com"),
])
def test_platform_titles_and_wildcard_domains_are_allowed_where_the_service_uses_them(service, field, value):
    assert sanitize({field: value}, service=service) == []
    assert [p.field for p in sanitize({field: value}, service="ec2")] == [field]


@pytest.mark.parametrize(("service", "field", "value"), [
    ("elasticbeanstalk", "SolutionStackName", "-running Docker"), ("elasticbeanstalk", "SolutionStackName", "a\nb"),
    ("acm", "DomainName", "*example.com"), ("acm", "DomainName", "a.*.example.com"), ("acm", "DomainName", "-x.com"),
])
def test_platform_titles_and_domains_still_refuse_other_values(service, field, value):
    assert [p.field for p in sanitize({field: value}, service=service)] == [field]


def test_an_auto_scaling_group_may_span_several_subnets():
    assert sanitize({"VPCZoneIdentifier": "subnet-0a1b2c3d,subnet-4e5f6a7b"}) == []
    assert [p.field for p in sanitize({"VPCZoneIdentifier": "subnet-0a1b2c3d;rm"})] == ["VPCZoneIdentifier"]
