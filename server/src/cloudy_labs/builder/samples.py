"""Code samples a generated op sends where the API takes bytes (a Lambda function's zip).

The learner never names a file: the CLI's `fileb://` would read any path on this machine. The
server picks the sample by id from `lambda_samples/`, zips it under the lab home once, and
puts only that path in the argv.
"""

import zipfile
from pathlib import Path

from .. import config

SAMPLES = Path(__file__).parent / "lambda_samples"
FIXED_TIME = (2020, 1, 1, 0, 0, 0)  # the same bytes on every build, so the code hash is stable


class SampleError(Exception):
    pass


def sample_ids() -> list[str]:
    return sorted(p.name for p in SAMPLES.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))


def sample_zip(sample: str) -> Path:
    """The zip of `sample`, built under the lab home when missing or older than its source."""
    if sample not in sample_ids():
        raise SampleError(f"no code sample named {sample!r}")
    src = SAMPLES / sample
    files = sorted(p for p in src.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    out = config.home() / "samples" / f"{sample}.zip"
    if out.exists() and all(out.stat().st_mtime >= f.stat().st_mtime for f in files):
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            info = zipfile.ZipInfo(f.relative_to(src).as_posix(), FIXED_TIME)
            info.external_attr = 0o644 << 16
            z.writestr(info, f.read_bytes(), zipfile.ZIP_DEFLATED)
    tmp.replace(out)
    return out
