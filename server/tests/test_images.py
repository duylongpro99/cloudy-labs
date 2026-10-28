import shutil

import pytest
import yaml

from cloudy_labs.emulator import images, stack

UPSTREAM = """\
defaultDockerImage: public.ecr.aws/amazonlinux/amazonlinux:2023

images:
  - imageId: ami-al2
    dockerImage: public.ecr.aws/amazonlinux/amazonlinux:2
    architecture: x86_64

  - imageId: ami-al2023
    dockerImage: public.ecr.aws/amazonlinux/amazonlinux:2023
    architecture: x86_64

  - imageId: ami-al2023-arm64
    dockerImage: public.ecr.aws/amazonlinux/amazonlinux:2023
    architecture: arm64
"""
NEW_DIGEST = "sha256:" + "a" * 64


def test_catalog_was_generated_from_the_floci_image_compose_runs():
    # Upgrading Floci in compose.yaml without `sync-catalog` fails here; the docker test
    # below compares the whole content.
    tag = images.floci_image().split("@")[0]
    assert f"from {tag}," in images.CATALOG_FILE.read_text().splitlines()[1]


def test_render_points_only_al2023_entries_at_the_image_for_their_architecture():
    rendered = images.render_catalog(UPSTREAM, "floci/floci:9.9.9@sha256:x", 7)
    catalog = yaml.safe_load(rendered)
    assert catalog["defaultDockerImage"] == images.UPSTREAM_AL2023
    assert {i["imageId"]: i["dockerImage"] for i in catalog["images"]} == {
        "ami-al2": "public.ecr.aws/amazonlinux/amazonlinux:2",
        "ami-al2023": "cloudy-labs/al2023:7-x86_64",
        "ami-al2023-arm64": "cloudy-labs/al2023:7-arm64",
    }
    assert "from floci/floci:9.9.9," in rendered


def test_render_refuses_an_architecture_without_a_built_image():
    with pytest.raises(ValueError, match="riscv64"):
        images.render_catalog(UPSTREAM.replace("arm64", "riscv64"), "floci/floci:9.9.9", 1)


@pytest.fixture
def files(tmp_path, monkeypatch):
    """Copies of the Dockerfile, stack.py and the catalog for bump_base to rewrite."""
    copies = {}
    for name in ("DOCKERFILE", "STACK_FILE", "CATALOG_FILE"):
        copies[name] = tmp_path / name
        shutil.copy(getattr(images, name), copies[name])
        monkeypatch.setattr(images, name, copies[name])
    return copies


def test_bump_base_pins_the_digest_and_moves_every_tag_to_the_next_version(files):
    version = stack.AL2023_VERSION
    assert images.bump_base(NEW_DIGEST) == version + 1
    assert f"amazonlinux:2023@{NEW_DIGEST}\n" in files["DOCKERFILE"].read_text()
    assert f"\nAL2023_VERSION = {version + 1}\n" in files["STACK_FILE"].read_text()
    tags = {i["dockerImage"] for i in yaml.safe_load(files["CATALOG_FILE"].read_text())["images"]}
    assert {stack.al2023_image(arch, version + 1) for arch in stack.AL2023_PLATFORMS} <= tags
    assert not any(tag.startswith(f"cloudy-labs/al2023:{version}-") for tag in tags)


def test_bump_base_leaves_files_alone_when_the_digest_is_already_pinned(files):
    pinned = images.FROM_LINE.search(files["DOCKERFILE"].read_text()).group(2)
    before = {name: path.read_text() for name, path in files.items()}
    assert images.bump_base(pinned) is None
    assert {name: path.read_text() for name, path in files.items()} == before
    assert images.bump_base(pinned, force=True) == stack.AL2023_VERSION + 1


@pytest.mark.docker
def test_catalog_matches_the_one_built_into_the_pinned_floci_image():
    image = images.floci_image()
    expected = images.render_catalog(images.embedded_catalog(image), image, stack.AL2023_VERSION)
    assert images.CATALOG_FILE.read_text() == expected, "run `python -m cloudy_labs.emulator.images sync-catalog`"
