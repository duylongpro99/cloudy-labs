"""Load lab definitions and resolve their checker functions.

Checker modules are Python files inside the lab directory and run with full privileges,
so only load labs from a trusted source (the labs that ship with the repo).
"""

import importlib.util
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import yaml
from pydantic import ValidationError

from ..config import labs_dir
from .content import ContentError, Tab, read_hints, read_tabs
from .schema import LAB_SLUG, Lab


class LabError(Exception):
    pass


@dataclass
class LoadedLab:
    lab: Lab
    path: Path
    _modules: dict[str, ModuleType] = field(default_factory=dict)

    def resolve(self, ref: str) -> Callable:
        module_name, fn_name = ref.split(":")
        module = self._modules.get(module_name)
        if module is None:
            file = self.path / f"{module_name}.py"
            if not file.is_file():
                raise LabError(f"{self.lab.id}: {ref}: no file {file}")
            # Unique module name per lab so two labs' checks.py never collide in sys.modules.
            spec = importlib.util.spec_from_file_location(f"cloudy_labs_lab.{self.lab.id}.{module_name}", file)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            # Registered like a normal import: dataclasses and typing look modules up in sys.modules.
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                del sys.modules[spec.name]
                raise LabError(f"{self.lab.id}: cannot import {file.name}: {e}") from e
            self._modules[module_name] = module
        fn = getattr(module, fn_name, None)
        if not callable(fn):
            raise LabError(f"{self.lab.id}: {ref}: {module_name}.py has no function {fn_name!r}")
        return fn

    def tabs(self) -> list[Tab] | None:
        """The theory tabs from `content/lab.md`, read each call so a fresh import shows at once."""
        return read_tabs(self.path)

    def hints(self) -> dict[str, list[str]]:
        """Hints per task: those of lab.yaml, replaced task by task by `content/hints.yaml`."""
        hints: dict[str, list[str]] = {}
        for h in self.lab.hints:
            hints.setdefault(h.task, []).append(h.text)
        try:
            hints.update(read_hints(self.path, {t.id for t in self.lab.tasks}))
        except ContentError as e:
            raise LabError(f"{self.lab.id}: {e}") from e
        return hints


def lab_path(lab_id: str, root: Path | None = None) -> Path:
    """The lab's directory. The id comes from the command line or the progress store, so it must be
    a plain slug that stays inside the labs directory."""
    base = (root or labs_dir()).resolve()
    if not isinstance(lab_id, str) or not re.fullmatch(LAB_SLUG, lab_id):
        raise LabError(f"{lab_id!r} is not a lab id: use lowercase letters, digits and dashes (at most 81)")
    path = (base / lab_id).resolve()
    if not path.is_relative_to(base):  # a symlinked lab directory pointing elsewhere
        raise LabError(f"lab {lab_id!r} resolves outside {base}")
    return path


def load_lab(lab_id: str, root: Path | None = None) -> LoadedLab:
    path = lab_path(lab_id, root)
    file = path / "lab.yaml"
    if not file.is_file():
        raise LabError(f"no lab {lab_id!r} (looked for {file})")
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
        lab = Lab.model_validate(data)
    except yaml.YAMLError as e:
        raise LabError(f"{file}: invalid YAML: {e}") from e
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc'])) or '(root)'}: {err['msg']}" for err in e.errors())
        raise LabError(f"{file}: {problems}") from e
    if lab.id != lab_id:
        raise LabError(f"{file}: id {lab.id!r} does not match directory name {lab_id!r}")
    loaded = LoadedLab(lab, path)
    loaded.hints()  # a broken content/hints.yaml fails here, like a broken lab.yaml
    # Resolve every reference now so a broken lab fails at load time, not halfway through a check run.
    for ref in [*lab.setup, *(c.fn for c in lab.checks)]:
        loaded.resolve(ref)
    return loaded


def list_labs(root: Path | None = None) -> list[str]:
    base = root or labs_dir()
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if (p / "lab.yaml").is_file())
