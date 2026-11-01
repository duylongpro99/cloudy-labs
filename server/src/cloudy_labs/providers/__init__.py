from ..config import DEFAULT_REGION
from ..labs import Lab, LabError
from .aws import AwsProvider
from .base import Provider

# (provider, emulator) pairs labctl knows how to run.
EMULATORS = [("aws", "floci"), ("aws", "moto")]


def get_provider(provider: str = "aws", emulator: str = "floci", region: str = DEFAULT_REGION) -> Provider:
    if (provider, emulator) not in EMULATORS:
        raise LabError(f"unsupported provider {provider!r} on emulator {emulator!r}")
    return AwsProvider(emulator, region)  # type: ignore[arg-type]


def provider_for(lab: Lab | None, region: str | None = None) -> Provider:
    """The provider a lab runs on, in its region (or `region`, one of its regions); without a lab,
    AWS on Floci in the default region."""
    if lab is None:
        return get_provider()
    return get_provider(lab.provider, lab.emulator, region or lab.region)


__all__ = ["EMULATORS", "AwsProvider", "Provider", "get_provider", "provider_for"]
