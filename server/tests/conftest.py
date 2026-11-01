from pathlib import Path

import pytest

FIXTURE_LABS = Path(__file__).parent / "fixtures" / "labs"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep tests away from the real ~/.cloudy-labs (progress and moto credentials) and from the
    learner's ~/.aws/config, which `labctl up` writes the lab profile into."""
    home = tmp_path / "home"
    monkeypatch.setenv("CLOUDY_LABS_HOME", str(home))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "aws-config"))
    return home


@pytest.fixture
def fixture_labs() -> Path:
    return FIXTURE_LABS


@pytest.fixture
def make_lab(tmp_path):
    """Write a lab directory under tmp_path and return the labs root."""

    def make(lab_id: str, yaml_text: str, checks_py: str = "") -> Path:
        d = tmp_path / "labs" / lab_id
        d.mkdir(parents=True)
        (d / "lab.yaml").write_text(yaml_text)
        if checks_py:
            (d / "checks.py").write_text(checks_py)
        return tmp_path / "labs"

    return make


REGISTRY_FIXTURES = Path(__file__).parent / "fixtures" / "registry"


@pytest.fixture
def extra_registry(monkeypatch):
    """Load the registry with an extra fixture directory (e.g. "test-only") for the rest of the test."""
    from cloudy_labs.registry import default_registry

    def use(*names: str):
        import os

        monkeypatch.setenv("CLOUDY_LABS_REGISTRY_EXTRA", os.pathsep.join(str(REGISTRY_FIXTURES / n) for n in names))
        default_registry.cache_clear()
        return default_registry()

    yield use
    default_registry.cache_clear()
