import json
from pathlib import Path

import pytest

from cloudy_labs import cli
from cloudy_labs.coverage import evaluate, extract, matrix
from cloudy_labs.registry import Registry, default_registry

# The verdicts below are judged against a registry that stays fixed while services are added:
# the network, database, storage, function and identity kinds, and nothing for DynamoDB, ELB or Cognito.
def _subset(services):
    """The kinds of `services` plus the structural ones. Edges to kinds outside the subset are
    dropped: verdicts do not read edges, and later services link to these kinds."""
    types = [t for t in default_registry().types if t.structural or t.service in services]
    kinds = {t.kind for t in types} | {"subnet"}
    return Registry([t.model_copy(update={"edges": [e for e in t.edges if set(e.to) <= kinds]}) for t in types])


REGISTRY = _subset({"ec2", "rds", "s3", "lambda", "iam"})

FIXTURES = Path(__file__).parent / "fixtures"
REAL_COMPOSE = evaluate.COMPOSE
VERSION, DIGEST = evaluate.pinned_image()
OTHER_DIGEST = "sha256:" + "0" * 64

PAGE = """# Lab: a VPC with a database

## Create the network

Create a VPC first.

```bash
VPC_ID=$(aws ec2 create-vpc \\
    --cidr-block 10.0.0.0/16 \\
    --query Vpc.VpcId --output text)
aws --region ap-southeast-2 ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.1.0/24 | jq .
aws configure list
```

Check it with `aws ec2 describe-vpcs --vpc-ids $VPC_ID` before going on.

## Store the files

```
aws s3 mb s3://lab-bucket && aws s3 cp ./a.txt s3://lab-bucket/
```

Put a Target Group in front of it later.
"""


def contract(kinds, digest=DIGEST, result="pass"):
    return {"floci_image_digest": digest, "date": "2026-10-31",
            "results": [{"kind": k, "op": f"create-{k}", "result": result, "seconds": 0.4} for k in kinds]}


@pytest.fixture
def evidence(tmp_path):
    def make(contract_data=None, overrides=evaluate.OVERRIDES):
        path = tmp_path / "contract-results.json"
        if contract_data is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(json.dumps(contract_data))
        return evaluate.Evidence.load(REGISTRY, compose=REAL_COMPOSE, contract_file=path, overrides_file=overrides)
    return make


def all_create_kinds():
    return [t.kind for t in REGISTRY.types if any(op.gesture == "create" for op in t.ops)]


def lab_dir(tmp_path, page: str, slug="lab-x") -> Path:
    d = tmp_path / "labs" / slug
    (d / "content").mkdir(parents=True)
    (d / "content" / "lab.md").write_text(page)
    return d


# extract ------------------------------------------------------------------------------------------


def test_commands_join_continued_lines_and_read_past_assignments_options_and_pipes():
    found = [(c.service, c.apis, c.line, c.heading) for c in extract.commands(PAGE)]
    assert found == [
        ("ec2", ("CreateVpc",), 8, "Create the network"),
        ("ec2", ("CreateSubnet",), 11, "Create the network"),
        ("ec2", ("DescribeVpcs",), 15, "Create the network"),
        ("s3", ("CreateBucket",), 20, "Store the files"),
        ("s3", ("PutObject", "GetObject"), 20, "Store the files"),
    ]
    [vpc] = [c for c in extract.commands(PAGE) if c.apis == ("CreateVpc",)]
    assert ("--cidr-block", "10.0.0.0/16") in vpc.flags


def test_a_shell_variable_value_and_an_unknown_operation_are_kept_apart():
    [cmd] = extract.commands("```\naws rds create-db-instance --engine $ENGINE\naws ec2 make-magic\n```\n")[:1]
    assert cmd.flags == (("--engine", "$ENGINE"),)
    unknown = extract.commands("```\naws ec2 make-magic\n```\n")
    assert unknown[0].service == "ec2" and unknown[0].apis == ()


@pytest.mark.parametrize("line, service, api", [
    ("aws s3api create-bucket --bucket b", "s3", "CreateBucket"),
    ("aws deploy create-application --application-name app", "codedeploy", "CreateApplication"),
    ("aws configservice put-config-rule --config-rule file://rule.json", "config", "PutConfigRule"),
])
def test_cli_command_names_map_to_the_api_service(line, service, api):
    [cmd] = extract.commands(f"```\n{line}\n```\n")
    assert (cmd.service, cmd.apis) == (service, (api,))


def test_a_cli_wait_maps_to_the_describe_api_it_polls():
    [cmd] = extract.commands("```\naws rds wait db-instance-available --db-instance-identifier db1\n```\n")
    assert (cmd.service, cmd.apis) == ("rds", ("DescribeDBInstances",))
    [unknown] = extract.commands("```\naws rds wait db-made-up\n```\n")
    assert (unknown.service, unknown.apis) == ("rds", ())

def test_sso_login_is_handled_by_the_cli_not_the_service():
    assert extract.commands("```\naws sso login --profile x\naws sso logout\n```\n") == []
    [cmd] = extract.commands("```\naws sso list-accounts --access-token t\n```\n")
    assert cmd.service == "sso"

def test_mentions_read_prose_only_prefer_longer_terms_and_split_certain_from_not():
    terms = extract.dictionary(REGISTRY)
    found = {(m.term, m.certain, m.line) for m in extract.mentions(PAGE, terms)}
    assert ("vpc", True, 5) in found
    assert ("target group", False, 23) in found
    assert not any(line in (8, 9, 10, 11, 12) for _, _, line in found)  # code blocks are not prose
    nat = extract.mentions("A NAT Gateway in the public subnet.\n", terms)
    assert {m.term for m in nat} == {"nat gateway", "subnet"}


def test_checker_services_reads_client_calls_without_running_them():
    src = 'def check(s):\n    s.client("rds").describe_db_instances()\n    boto3.client(\'ec2\', region_name=r)\n'
    assert extract.checker_services([src]) == {"rds", "ec2"}


# one lab ------------------------------------------------------------------------------------------


def test_floci_lacking_an_api_blocks_the_lab(tmp_path, evidence):
    d = lab_dir(tmp_path, "## Back up\n\n```\naws ec2 create-snapshot --volume-id vol-1\n```\n")
    report = evaluate.evaluate_lab(d, evidence(contract(all_create_kinds())))
    assert report.verdict == "blocked"
    codes = {f.code for f in report.findings}
    assert {"floci-missing-api", "catalog-override"} <= codes
    [missing] = [f for f in report.findings if f.code == "floci-missing-api"]
    assert missing.line == 4 and missing.heading == "Back up" and "ec2:CreateSnapshot" in missing.text


def test_an_override_matches_a_flag_value(tmp_path, evidence):
    d = lab_dir(tmp_path, "```\naws rds create-db-instance --engine oracle-ee --db-instance-identifier db1\n```\n")
    report = evaluate.evaluate_lab(d, evidence(contract(all_create_kinds())))
    assert report.verdict == "blocked"
    assert any(f.code == "catalog-override" and f.text.startswith("rds-oracle") for f in report.findings)
    mysql = lab_dir(tmp_path, "```\naws rds create-db-instance --engine mysql --db-instance-identifier db1\n```\n", "lab-y")
    assert not any(f.code == "catalog-override" for f in evaluate.evaluate_lab(mysql, evidence(contract([]))).findings)


def test_floci_lacking_a_service_blocks_the_lab(tmp_path, evidence):
    d = lab_dir(tmp_path, "```\naws fsx create-file-system --file-system-type LUSTRE\n```\n")
    report = evaluate.evaluate_lab(d, evidence(contract(all_create_kinds())))
    assert report.verdict == "blocked"
    assert any(f.code == "floci-missing-service" and "fsx" in f.text for f in report.findings)


def test_a_service_floci_has_but_the_registry_lacks_is_a_gap(tmp_path, evidence):
    d = lab_dir(tmp_path, "```\naws sqs create-queue --queue-name q\n```\n")
    report = evaluate.evaluate_lab(d, evidence(contract(all_create_kinds())))
    assert report.verdict == "gap"
    codes = {f.code for f in report.findings}
    assert codes == {"no-kind-for-service", "no-kind-for-api"}


def test_a_failed_contract_test_is_a_gap(tmp_path, evidence):
    d = lab_dir(tmp_path, "```\naws ec2 create-vpc --cidr-block 10.0.0.0/16\n```\n")
    report = evaluate.evaluate_lab(d, evidence(contract(["vpc"], result="fail")))
    assert report.verdict == "gap"
    assert [f.code for f in report.findings] == ["contract-failed"]


def test_registry_caveats_and_unrun_contracts_give_ready_with_caveats(tmp_path, evidence):
    d = lab_dir(tmp_path, "```\naws ec2 create-vpc --cidr-block 10.0.0.0/16\naws ec2 create-route-table --vpc-id v\n```\n")
    report = evaluate.evaluate_lab(d, evidence(None))
    assert report.verdict == "ready-with-caveats"
    assert {f.code for f in report.findings} == {"contract-not-run", "reachability-analysed"}
    assert report.warnings and "no contract test results" in report.warnings[0]


def test_a_lab_with_everything_covered_is_ready(tmp_path, evidence):
    d = lab_dir(tmp_path, "## Network\n\nMake a VPC.\n\n```\naws ec2 create-vpc --cidr-block 10.0.0.0/16\n```\n")
    report = evaluate.evaluate_lab(d, evidence(contract(all_create_kinds())))
    assert (report.verdict, report.findings, report.draft, report.warnings) == ("ready", [], False, [])
    assert report.kinds == ["vpc"] and report.services == ["ec2"]


def test_a_lab_yaml_alone_is_judged_by_its_palette_target_and_checks(evidence):
    report = evaluate.evaluate_lab(FIXTURES / "labs" / "fixture-lab-06", evidence(contract(all_create_kinds())), review={})
    assert report.verdict == "ready-with-caveats"
    assert {"vpc", "igw", "route-table"} <= set(report.kinds) and report.services == ["ec2"]
    assert [f.code for f in report.findings] == ["reachability-analysed"]


def test_a_contract_run_on_another_image_warns(evidence):
    ev = evidence(contract(["vpc"], digest=OTHER_DIGEST))
    [warning] = ev.warnings()
    assert OTHER_DIGEST in warning and DIGEST in warning


def test_unreviewed_names_keep_the_verdict_a_draft_until_accepted(tmp_path, evidence):
    d = lab_dir(tmp_path, PAGE)
    ev = evidence(contract(all_create_kinds()))
    first = evaluate.evaluate_lab(d, ev)
    assert first.draft and {u["term"] for u in first.unrecognised} == {"target group"}
    assert first.verdict == "ready-with-caveats" and "elbv2" not in first.services  # the unsure name is not counted

    evaluate.write_review(d, [u["line"] for u in first.unrecognised], require=set())
    accepted = evaluate.evaluate_lab(d, ev)
    assert not accepted.draft and accepted.verdict == first.verdict

    evaluate.write_review(d, [], require={23})
    required = evaluate.evaluate_lab(d, ev)
    assert required.verdict == "gap" and len(required.findings) == len(first.findings) + 2  # requirement + elbv2 kind gap
    assert any(f.code == "reviewed-requirement" and f.line == 23 for f in required.findings)
    assert "elbv2" in required.services
    assert set(json.loads((d / "coverage-review.json").read_text())) == {"reviewed", "lines"}


def test_an_optional_step_the_emulator_lacks_is_a_caveat_not_a_blocker(tmp_path, evidence):
    d = lab_dir(tmp_path, "## Back up (optional)\n\n```\naws ec2 create-snapshot --volume-id vol-1\n```\n")
    ev = evidence(contract(all_create_kinds()))
    assert evaluate.evaluate_lab(d, ev).verdict == "blocked"

    evaluate.write_review(d, [], require=set(), optional=frozenset({4}))
    report = evaluate.evaluate_lab(d, ev)
    assert report.verdict == "ready-with-caveats"
    optional = [f for f in report.findings if f.line == 4]
    assert {f.code for f in optional} == {"optional-step-unsupported"} and len(optional) == 2  # missing API + override
    assert all(f.level == "caveat" for f in optional)
    assert json.loads((d / "coverage-review.json").read_text())["lines"] == {"4": "optional"}


def test_accept_refuses_an_optional_line_without_a_command(tmp_path, evidence, monkeypatch, capsys):
    d = lab_dir(tmp_path, PAGE, "lab-opt")
    ev = evidence(contract(all_create_kinds()))
    monkeypatch.setattr(evaluate.Evidence, "load", classmethod(lambda cls, **_: ev))
    monkeypatch.setattr("cloudy_labs.labs.lab_path", lambda slug: tmp_path / "labs" / slug)
    assert cli.main(["coverage", "lab-opt", "--accept", "--optional", "3"]) == 1
    assert "no aws command: 3" in capsys.readouterr().err
    assert not (d / "coverage-review.json").exists()


def test_an_override_named_only_in_prose_is_listed_for_review_not_counted(tmp_path, evidence):
    d = lab_dir(tmp_path, "## Compare engines\n\nOracle is not used here.\n")
    report = evaluate.evaluate_lab(d, evidence(contract(all_create_kinds())))
    assert report.draft and report.verdict == "ready"
    assert [(u["line"], u["term"]) for u in report.unrecognised] == [(3, "rds-oracle")]


def test_the_json_report_never_carries_the_page_text(tmp_path, evidence, monkeypatch, capsys):
    secret_prose = "Zanzibar quokka sentence that must stay local"
    page = PAGE + f"\n{secret_prose} next to a Target Group.\n"
    d = lab_dir(tmp_path, page, "lab-json")
    ev = evidence(contract(all_create_kinds()))
    monkeypatch.setattr(evaluate.Evidence, "load", classmethod(lambda cls, **_: ev))
    monkeypatch.setattr("cloudy_labs.labs.lab_path", lambda slug: tmp_path / "labs" / slug)
    assert cli.main(["coverage", "lab-json", "--json", "--quote"]) == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["lab"] == "lab-json" and report["draft"]
    assert "quokka" not in out and "Put a" not in out and "10.0.0.0" not in out

    assert cli.main(["coverage", "lab-json", "--quote"]) == 0
    assert "quokka" in capsys.readouterr().out  # --quote shows the line in this terminal

    assert cli.main(["coverage", "lab-json", "--accept", "--require", "23"]) == 0
    review = (d / "coverage-review.json").read_text()
    assert "quokka" not in review and "Target" not in review


# the catalog --------------------------------------------------------------------------------------

CSV_HEADER = "slug,title,toc,api_namespaces,floci_missing,floci_fit\n"
CSV_ROWS = [
    "lab-a-vpc,Tạo VPC,Subnet | Route table,ec2,,api-covered",
    "lab-b-snap,Tạo EBS Snapshot,Restore,ec2,,api-covered",
    "lab-c-fsx,FSx for Lustre,,fsx,FSx,blocked",
    "lab-d-ddb,DynamoDB table,,dynamodb,,api-covered",
    "lab-e-think,Thiết kế naming,,,,api-covered",
    "lab-f-sts,Ký request,,sts,,api-covered",
    "lab-g-cog,Cognito user pool,,cognito,,api-covered",
    "lab-h-cp,Replication,,ec2,,control-plane-only",
]


@pytest.fixture
def catalog(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text(CSV_HEADER + "\n".join(CSV_ROWS) + "\n", encoding="utf-8")
    return path


def test_every_catalog_row_gets_the_verdict_its_metadata_supports(catalog, evidence):
    ev = evidence(contract(all_create_kinds()))
    verdicts = {r["slug"]: evaluate.evaluate_row(r, ev).verdict for r in evaluate.read_catalog(catalog)}
    assert verdicts == {
        "lab-a-vpc": "ready-with-caveats",  # reachability is analysed statically
        "lab-b-snap": "blocked",  # the ebs-snapshot override
        "lab-c-fsx": "blocked",
        "lab-d-ddb": "gap",  # no dynamodb kind yet
        "lab-e-think": "ready-with-caveats",  # no API named: the page decides
        "lab-f-sts": "ready",
        "lab-g-cog": "gap",  # cognito -> cognito-idp, which Floci has and the registry lacks
        "lab-h-cp": "ready-with-caveats",
    }
    codes = {r["slug"]: {f.code for f in evaluate.evaluate_row(r, ev).findings} for r in evaluate.read_catalog(catalog)}
    assert "namespace-level" in codes["lab-h-cp"] and "namespace-level" not in codes["lab-e-think"]


def test_a_catalog_row_is_never_ready_on_its_services_alone(evidence):
    ev = evidence(contract(all_create_kinds()))

    def row(title, toc=""):
        report = evaluate.evaluate_row({"slug": "lab-x", "title": title, "toc": toc, "api_namespaces": "ec2"}, ev)
        return report.verdict, {f.code for f in report.findings}

    # EC2 has kinds, but not necessarily the ones an EBS lab makes; a caveat of any EC2 kind is shown.
    assert row("Mở rộng EBS gp3", "Resize ; fstab") == ("ready-with-caveats", {"namespace-level", "ebs-snapshot-missing"})
    # A resource the outline names that only botocore knows is a kind still to add.
    verdict, codes = row("Site-to-Site VPN", "Customer Gateway ; Kiểm tra")
    assert verdict == "gap" and "no-kind-for-resource" in codes and "namespace-level" not in codes
    # Signing requests makes no resource at all.
    sts = evaluate.evaluate_row({"slug": "lab-y", "title": "SigV4", "toc": "", "api_namespaces": "sts"}, ev)
    assert sts.verdict == "ready"


def test_an_excluded_slug_escapes_its_override(evidence):
    row = {"slug": "lab-042-tao-aurora-postgresql-cluster", "title": "Aurora with Babelfish for SQL Server clients",
           "toc": "", "api_namespaces": "rds"}
    assert not any(f.code == "catalog-override" for f in evaluate.evaluate_row(row, evidence(None)).findings)


def test_the_catalog_summary_counts_verdicts_services_and_reasons(catalog, evidence, monkeypatch, capsys):
    summary = evaluate.evaluate_catalog(evaluate.read_catalog(catalog), evidence(None))
    assert summary.total == 8 and sum(summary.by_verdict.values()) == 8
    assert summary.by_service["ec2"]["blocked"] == 1
    assert summary.reasons["the registry has no kind of dynamodb"] == 1

    ev = evidence(contract(all_create_kinds()))
    monkeypatch.setattr(evaluate.Evidence, "load", classmethod(lambda cls, **_: ev))
    assert cli.main(["coverage", "--catalog", str(catalog), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["total"] == 8 and "metadata" in out["note"] and len(out["labs"]) == 8


def test_strict_fails_on_stale_contract_results(catalog, evidence, monkeypatch, capsys):
    ev = evidence(contract(["vpc"], OTHER_DIGEST))
    monkeypatch.setattr(evaluate.Evidence, "load", classmethod(lambda cls, **_: ev))
    assert cli.main(["coverage", "--catalog", str(catalog), "--strict"]) == 1
    assert "rerun the contract tests" in capsys.readouterr().err
    assert cli.main(["coverage", "--catalog", str(catalog)]) == 0


def test_a_missing_lab_is_a_plain_error_not_a_crash(tmp_path, evidence, monkeypatch, capsys):
    ev = evidence(contract(["vpc"]))
    monkeypatch.setattr(evaluate.Evidence, "load", classmethod(lambda cls, **_: ev))
    monkeypatch.setattr("cloudy_labs.labs.lab_path", lambda slug: tmp_path / "labs" / slug)
    assert cli.main(["coverage", "no-such-lab"]) == 1
    err = capsys.readouterr().err
    assert "no lab.yaml" in err and "unexpected error" not in err


def test_a_compose_file_without_a_pinned_image_is_an_error(tmp_path):
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  floci:\n    image: floci/floci:latest\n")
    with pytest.raises(evaluate.CoverageError, match="no pinned"):
        evaluate.pinned_image(compose)


# the matrix ---------------------------------------------------------------------------------------


def test_the_committed_matrix_is_what_the_generator_writes():
    ev = evaluate.Evidence.load()
    assert matrix.DOC.read_text() == matrix.render(ev), "run `uv run labctl coverage --matrix`"


def test_writing_the_matrix_twice_changes_nothing(tmp_path, evidence):
    ev = evidence(contract(["vpc"], result="fail"))
    path = tmp_path / "coverage.md"
    assert matrix.write(ev, path) and not matrix.write(ev, path)
    text = path.read_text()
    assert "| ec2 | `vpc` |" in text and "fail (create-vpc), ≤0.4s" in text and "| ec2 | `az` |" in text


def test_every_kind_the_builder_creates_declares_a_contract_of_ops_that_exist():
    from cloudy_labs.builder.catalog import op_named

    for t in default_registry().types:
        if t.test_only or not any(op.gesture == "create" for op in t.ops):
            continue
        assert t.contract, f"{t.kind} has a create op but no contract"
        for step in [*t.contract.needs, t.contract.create, *t.contract.then]:
            assert op_named(step.op) is not None, f"{t.kind}: no op {step.op}"
        assert t.contract.parent is None or t.contract.parent in {s.save for s in t.contract.needs}
