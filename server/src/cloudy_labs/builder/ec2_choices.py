"""AMIs and instance types the builder offers, by the host's CPU architecture.

Only AMIs in the emulator's image catalog (emulator/ec2-image-catalog.yaml) start from the
prebuilt image; any other id falls back to a slow install at boot. An instance of the other
architecture runs under emulation, so each host gets the images and types native to it.
"""

import platform
from typing import TypedDict


class Choices(TypedDict):
    images: list[str]
    instanceTypes: list[str]


_ARM = Choices(images=["ami-amazonlinux2023-arm64"], instanceTypes=["t4g.micro", "t4g.small"])
_X86 = Choices(images=["ami-amazonlinux2023"], instanceTypes=["t3.micro", "t3.small"])
_BY_MACHINE = {"arm64": _ARM, "aarch64": _ARM, "x86_64": _X86, "amd64": _X86}


def choices(machine: str | None = None) -> Choices:
    """Pure for a given `machine`; defaults to this host's (`platform.machine()`)."""
    found = _BY_MACHINE.get((machine or platform.machine()).lower(), _X86)
    return Choices(images=list(found["images"]), instanceTypes=list(found["instanceTypes"]))
