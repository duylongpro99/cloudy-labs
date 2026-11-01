"""A lab's local content: the theory the learner pasted (`content/lab.md`), the hints written for it
(`content/hints.yaml`) and the images it shows.

`labs/<slug>/content/` is gitignored: lab text taken from a course site is for the learner's own use,
never committed and never sent to the chat model. Only the lab server reads it, to show it in the app.
"""

import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

CONTENT_DIR = "content"
LAB_MD = "lab.md"
HINTS_YAML = "hints.yaml"
INTRO_TITLE = "Giới thiệu"
IMAGE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,100}\.(png|jpg|jpeg|gif|webp|svg)$", re.IGNORECASE)
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
               "webp": "image/webp", "svg": "image/svg+xml"}
IMAGE_MAX_BYTES = 10 * 1024 * 1024
FETCH_TIMEOUT_S = 20

_H2 = re.compile(r"^##(?!#)\s*(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_URL = re.compile(r"https?://[^\s)<>\"']+")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*(<[^>]*>|[^\s)]+)(\s+\"[^\"]*\")?\s*\)")


class ContentError(Exception):
    pass


@dataclass(frozen=True)
class Tab:
    title: str
    markdown: str


def content_dir(lab_dir: Path) -> Path:
    return lab_dir / CONTENT_DIR


def split_tabs(markdown: str) -> list[Tab]:
    """One tab per level-2 heading. Text before the first one becomes the intro tab when it has any;
    headings inside fenced code blocks are text, not tabs."""
    tabs: list[Tab] = []
    title, lines, fence = INTRO_TITLE, [], None
    for line in markdown.splitlines():
        if m := _FENCE.match(line):
            fence = None if fence == m.group(1) else (fence or m.group(1))
        elif fence is None and (h := _H2.match(line)):
            tabs.append(Tab(title, "\n".join(lines).strip("\n")))
            title, lines = h.group(1) or "(không tên)", []
            continue
        lines.append(line)
    tabs.append(Tab(title, "\n".join(lines).strip("\n")))
    if not tabs[0].markdown.strip():  # the first tab is always the text before any heading
        tabs.pop(0)
    return tabs


def read_tabs(lab_dir: Path) -> list[Tab] | None:
    """The theory tabs, or None when the lab has no `content/lab.md`."""
    file = content_dir(lab_dir) / LAB_MD
    if not file.is_file():
        return None
    return split_tabs(file.read_text(encoding="utf-8"))


def read_hints(lab_dir: Path, task_ids: set[str]) -> dict[str, list[str]]:
    """`content/hints.yaml` as {task id: [hint, ...]}; empty when the file is missing."""
    file = content_dir(lab_dir) / HINTS_YAML
    if not file.is_file():
        return {}
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ContentError(f"{file}: invalid YAML: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ContentError(f"{file}: expected a mapping of task id to a list of hints")
    hints: dict[str, list[str]] = {}
    for task, items in data.items():
        if task not in task_ids:
            raise ContentError(f"{file}: hint for unknown task {task!r}")
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, list) or not all(isinstance(i, str) and i.strip() for i in items):
            raise ContentError(f"{file}: hints for {task!r} must be a list of non-empty strings")
        hints[task] = items
    return hints


def image_file(lab_dir: Path, name: str) -> Path:
    """The image `name` inside the lab's content directory; ContentError for anything else."""
    if not IMAGE_NAME.fullmatch(name):
        raise ContentError("not an image name")
    base = content_dir(lab_dir).resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or not path.is_file():  # a symlink pointing elsewhere, or missing
        raise ContentError("no such image")
    return path


def image_type(name: str) -> str:
    return IMAGE_TYPES[name.rsplit(".", 1)[1].lower()]


def strip_presigned(markdown: str) -> str:
    """Drop the `X-Amz-*` query parameters of S3 presigned URLs: they are short-lived credentials."""
    def clean(m: re.Match) -> str:
        parts = urllib.parse.urlsplit(m.group(0))
        query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith("x-amz-")]
        if len(query) == len(urllib.parse.parse_qsl(parts.query, keep_blank_values=True)):
            return m.group(0)
        return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
    return _URL.sub(clean, markdown)


def _local_name(url: str, taken: set[str]) -> str | None:
    base = Path(urllib.parse.urlsplit(url).path).name
    stem, dot, ext = base.rpartition(".")
    if not dot or ext.lower() not in IMAGE_TYPES:
        return None
    stem = re.sub(r"[^A-Za-z0-9._-]", "-", stem)[:80].strip(".") or "image"
    name, n = f"{stem}.{ext.lower()}", 1
    while name in taken:
        n += 1
        name = f"{stem}-{n}.{ext.lower()}"
    taken.add(name)
    return name


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_S) as response:  # noqa: S310 (http/https only, see caller)
        data = response.read(IMAGE_MAX_BYTES + 1)
    if len(data) > IMAGE_MAX_BYTES:
        raise ContentError(f"image larger than {IMAGE_MAX_BYTES // (1024 * 1024)} MB")
    return data


def fetch_images(markdown: str, dest: Path, download=_download) -> tuple[str, list[str]]:
    """Download the http(s) images the markdown shows into `dest` and point the markdown at the local
    copies. Returns the new markdown and one line per image that could not be fetched."""
    taken = {p.name for p in dest.iterdir()} if dest.is_dir() else set()
    problems: list[str] = []

    def replace(m: re.Match) -> str:
        url = m.group(2).strip("<>")
        if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
            return m.group(0)
        name = _local_name(url, taken)
        if name is None:
            problems.append(f"skipped {urllib.parse.urlsplit(url).netloc}: not a png, jpg, gif, webp or svg")
            return m.group(0)
        try:
            data = download(url)
        except Exception as e:  # network errors and the size cap alike: keep the link, report it
            taken.discard(name)
            problems.append(f"could not fetch {name}: {type(e).__name__}: {e}")
            return m.group(0)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / name).write_bytes(data)
        return f"![{m.group(1)}]({name}{m.group(3) or ''})"

    return _IMAGE.sub(replace, markdown), problems


def import_content(lab_dir: Path, source: Path, fetch: bool = False, download=_download) -> tuple[list[Tab], list[str]]:
    """Copy a pasted lab page into `content/lab.md`, without presigned credentials. Returns the tabs
    and any image problems."""
    markdown = strip_presigned(source.read_text(encoding="utf-8"))
    dest = content_dir(lab_dir)
    problems: list[str] = []
    if fetch:
        markdown, problems = fetch_images(markdown, dest, download)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / LAB_MD).write_text(markdown, encoding="utf-8")
    return split_tabs(markdown), problems
