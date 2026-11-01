import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloudy_labs.chat.settings import LlmSettings
from cloudy_labs.cli import main
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.labs import LabError, load_lab
from cloudy_labs.labs.content import ContentError, fetch_images, image_file, split_tabs, strip_presigned
from cloudy_labs.progress import Attempt
from cloudy_labs.server.app import create_app

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).parents[2]
GOLDEN = ResourceGraph.model_validate_json((FIXTURES / "graph" / "lab-06-07.graph.json").read_text())
ORIGIN = {"Origin": "http://127.0.0.1:5174"}
# Written for these tests; real course pages are never in the repo.
PAGE = """Bài này dựng một mạng nhỏ để thử định tuyến.

## Mục tiêu

| Bước | Việc |
|---|---|
| 1 | Tạo VPC |

## Các bước

```bash
## not a heading inside a fence
aws ec2 create-vpc
```

![sơ đồ](diagram.png)

### Chi tiết
Sentence the chat model must never see: violet otters audit the routing tables at dawn.
"""
SECRET_SENTENCE = "violet otters audit the routing tables at dawn"


@pytest.fixture
def lab06(tmp_path):
    """fixture-lab-06 copied so the test can give it local content."""
    root = tmp_path / "labs"
    shutil.copytree(FIXTURES / "labs" / "fixture-lab-06", root / "fixture-lab-06")
    return root


def write_content(root: Path, lab: str, files: dict[str, str | bytes]) -> Path:
    d = root / lab / "content"
    d.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (d / name).write_bytes(data if isinstance(data, bytes) else data.encode())
    return d


def test_tabs_follow_level_two_headings():
    tabs = split_tabs(PAGE)
    assert [t.title for t in tabs] == ["Giới thiệu", "Mục tiêu", "Các bước"]
    assert tabs[0].markdown == "Bài này dựng một mạng nhỏ để thử định tuyến."
    assert "| 1 | Tạo VPC |" in tabs[1].markdown
    assert "## not a heading inside a fence" in tabs[2].markdown and "### Chi tiết" in tabs[2].markdown


def test_no_intro_tab_without_text_before_the_first_heading():
    assert [t.title for t in split_tabs("\n## A\none\n## B ##\ntwo")] == ["A", "B"]
    assert split_tabs("") == [] and [t.title for t in split_tabs("just text")] == ["Giới thiệu"]


def test_hints_from_content_win_task_by_task(lab06):
    loaded = load_lab("fixture-lab-06", lab06)
    from_yaml = loaded.hints()
    assert from_yaml and all(isinstance(v, list) for v in from_yaml.values())
    task = loaded.lab.tasks[0].id
    write_content(lab06, "fixture-lab-06", {"hints.yaml": f"{task}:\n  - gợi ý riêng\n"})
    hints = loaded.hints()
    assert hints[task] == ["gợi ý riêng"]
    assert {k: v for k, v in hints.items() if k != task} == {k: v for k, v in from_yaml.items() if k != task}


@pytest.mark.parametrize("text, needle", [
    ("nope:\n  - x\n", "unknown task"),
    ("- a list\n", "mapping"),
    ("vpc: [1]\n", "non-empty strings"),
    ("a: [\n", "invalid YAML"),
])
def test_a_broken_hints_file_fails_the_load(lab06, text, needle):
    write_content(lab06, "fixture-lab-06", {"hints.yaml": text})
    with pytest.raises(LabError, match=needle):
        load_lab("fixture-lab-06", lab06)


def test_presigned_query_is_dropped_and_other_query_kept():
    url = ("https://bucket.s3.amazonaws.com/a.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAEXAMPLE"
           "&x-amz-signature=abc&width=300")
    out = strip_presigned(f"![a]({url}) and https://example.com/?q=1")
    assert "AKIAEXAMPLE" not in out and "X-Amz" not in out and "x-amz" not in out
    assert "https://bucket.s3.amazonaws.com/a.png?width=300" in out and "https://example.com/?q=1" in out


def test_fetch_images_points_the_page_at_local_copies(tmp_path):
    md = "![a](https://cdn.example/img/net%20map.PNG) ![b](https://cdn.example/x.exe) ![c](local.png) ![d](https://cdn.example/gone.png)"

    def download(url):
        if "gone" in url:
            raise OSError("404")
        return b"\x89PNG"

    out, problems = fetch_images(md, tmp_path, download)
    assert "![a](net-20map.png)" in out and (tmp_path / "net-20map.png").read_bytes() == b"\x89PNG"
    assert "https://cdn.example/x.exe" in out and "![c](local.png)" in out and "https://cdn.example/gone.png" in out
    assert len(problems) == 2 and not (tmp_path / "gone.png").exists()


def test_content_import_writes_the_page_and_lists_tabs(lab06, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLOUDY_LABS_LABS_DIR", str(lab06))
    src = tmp_path / "page.md"
    src.write_text(PAGE + "\n![x](https://b.s3.amazonaws.com/x.png?X-Amz-Signature=deadbeef)\n")
    assert main(["content", "import", "fixture-lab-06", str(src)]) == 0
    written = (lab06 / "fixture-lab-06" / "content" / "lab.md").read_text()
    assert "deadbeef" not in written and SECRET_SENTENCE in written
    assert "3 tab(s)" in capsys.readouterr().out
    assert main(["content", "import", "../etc", str(src)]) == 1
    assert main(["content", "import", "fixture-lab-06", str(tmp_path / "missing.md")]) == 1


@pytest.mark.parametrize("name", ["../lab.yaml", "lab.md", "x.html", "a b.png", ".png", "x" * 101 + ".png", "missing.png"])
def test_image_names_outside_the_rules_are_refused(lab06, name):
    write_content(lab06, "fixture-lab-06", {"lab.md": "x", "ok.png": b"\x89PNG"})
    with pytest.raises(ContentError):
        image_file(lab06 / "fixture-lab-06", name)


def test_a_symlinked_image_pointing_outside_is_refused(lab06, tmp_path):
    d = write_content(lab06, "fixture-lab-06", {})
    (tmp_path / "secret.png").write_bytes(b"x")
    (d / "link.png").symlink_to(tmp_path / "secret.png")
    with pytest.raises(ContentError):
        image_file(lab06 / "fixture-lab-06", "link.png")


@pytest.fixture
def served(lab06):
    state = {"asked": []}
    loaded = load_lab("fixture-lab-06", lab06)

    async def complete(settings, system, messages):
        state["asked"].append(system + json.dumps(messages, ensure_ascii=False))
        return json.dumps({"reply": "ok", "refusal": None, "steps": []})

    app = create_app(lambda: GOLDEN, listen=False, lab=lambda: (loaded, Attempt(1, "fixture-lab-06", "")),
                     checks_runner=lambda loaded: [], azs=lambda: ["ap-southeast-2a", "ap-southeast-2b"],
                     blocker=lambda: None, llm=lambda: LlmSettings("https://llm.example/v1", "k", "m", "openai"),
                     complete=complete)
    with TestClient(app, base_url="http://127.0.0.1:8730") as client:
        yield client, state, lab06


def test_api_lab_has_tabs_and_hints(served):
    client, _, root = served
    body = client.get("/api/lab").json()
    assert body["content"] is None and body["hints"]
    write_content(root, "fixture-lab-06", {"lab.md": PAGE})
    body = client.get("/api/lab").json()
    assert [t["title"] for t in body["content"]] == ["Giới thiệu", "Mục tiêu", "Các bước"]


def test_api_lab_reports_a_hints_file_broken_after_loading(served):
    client, _, root = served
    write_content(root, "fixture-lab-06", {"hints.yaml": "nope: [x]\n"})
    r = client.get("/api/lab")
    assert r.status_code == 409 and "unknown task" in r.json()["detail"]


def test_image_endpoint_serves_only_the_open_labs_images(served):
    client, _, root = served
    write_content(root, "fixture-lab-06", {"diagram.png": b"\x89PNG", "map.svg": "<svg xmlns='http://www.w3.org/2000/svg'/>"})
    r = client.get("/api/lab/content/diagram.png")
    assert r.status_code == 200 and r.content == b"\x89PNG" and r.headers["content-type"] == "image/png"
    assert r.headers["x-content-type-options"] == "nosniff"
    svg = client.get("/api/lab/content/map.svg")
    assert svg.headers["content-security-policy"] == "sandbox" and svg.headers["content-type"].startswith("image/svg+xml")
    for bad in ["..%2Flab.yaml", "lab.yaml", "missing.png", "x.html"]:
        assert client.get(f"/api/lab/content/{bad}").status_code == 404
    assert client.get("/api/lab/content/diagram.png", headers={"Host": "evil.example"}).status_code == 400


def test_lab_content_never_reaches_the_chat_model(served):
    client, state, root = served
    write_content(root, "fixture-lab-06", {"lab.md": PAGE, "hints.yaml": f"vpc:\n  - {SECRET_SENTENCE}\n"})
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "làm gì tiếp?"}]}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    [sent] = state["asked"]
    assert SECRET_SENTENCE not in sent and "Mục tiêu" not in sent and "violet otters" not in sent


def test_lab_content_directories_are_gitignored():
    out = subprocess.run(["git", "-C", str(REPO), "check-ignore", "labs/any-lab/content/lab.md",
                          "labs/any-lab/content/hints.yaml", "labs/any-lab/content/diagram.png"],
                         capture_output=True, text=True)
    assert out.returncode == 0 and len(out.stdout.split()) == 3
    kept = subprocess.run(["git", "-C", str(REPO), "check-ignore", "labs/any-lab/lab.yaml"], capture_output=True)
    assert kept.returncode == 1


def test_leak_check_finds_copied_text_without_printing_it(tmp_path):
    repo = tmp_path / "repo"
    (repo / "labs" / "x" / "content").mkdir(parents=True)
    (repo / ".gitignore").write_text("labs/*/content/\n")
    (repo / "labs" / "x" / "content" / "lab.md").write_text("Sentence the chat model must never see: " + SECRET_SENTENCE)
    (repo / "notes.md").write_text("quoting it here: " + SECRET_SENTENCE + " oops")
    (repo / "clean.md").write_text("violet otters only")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    script = Path(__file__).parents[1] / "scripts" / "check-content-leak.py"
    spec = importlib.util.spec_from_file_location("check_content_leak", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.leaks(repo) == {"notes.md": 1}
    run = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=REPO / "server")
    assert run.returncode == 0, run.stdout + run.stderr  # the real repo has no copied content


def test_leak_check_skips_the_public_catalog_and_reviewed_idioms(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "check-content-leak.py"
    spec = importlib.util.spec_from_file_location("check_content_leak", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    title = "Lab 999 build a shared network across three zones with care"
    idiom = "aws ec2 describe-flow-logs --filter Name=resource-id,Values=vpc-1 --query FlowLogs"
    repo = tmp_path / "repo"
    (repo / "labs" / "x" / "content").mkdir(parents=True)
    (repo / ".gitignore").write_text("labs/*/content/\n")
    (repo / "labs" / "x" / "content" / "lab.md").write_text(f"# {title}\n\n{idiom}\n\n{SECRET_SENTENCE}\n")
    (repo / Path(module.PUBLIC_CATALOG).parent).mkdir(parents=True)
    (repo / module.PUBLIC_CATALOG).write_text(f"slug,title\nlab-999,{title}\n")
    (repo / "notes.md").write_text(f"{title}\nand\n{idiom}\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    [(_, idiom_runs)] = module.shared_runs(repo).items()
    assert idiom_runs == module.ngrams(idiom)  # the title is public, the idiom not reviewed yet
    reviewed = {module.run_hash(r): "a CLI filter" for r in idiom_runs}
    (repo / "labs" / "x" / module.REVIEW_FILE).write_text(json.dumps({"reviewed": "2026-11-01", "runs": reviewed}))
    assert module.leaks(repo) == {}
    (repo / "notes.md").write_text(f"{title}\nand\n{SECRET_SENTENCE}\n")
    assert module.leaks(repo) == {"notes.md": len(module.ngrams(SECRET_SENTENCE))}
