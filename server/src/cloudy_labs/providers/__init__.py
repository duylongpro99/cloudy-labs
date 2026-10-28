from ..labs import Lab, LabError
from .aws import AwsProvider
from .base import Provider

# (provider, emulator) pairs labctl knows how to run.
EMULATORS = [("aws", "floci"), ("aws", "moto")]


def get_provider(provider: str = "aws", emulator: str = "floci") -> Provider:
    if (provider, emulator) not in EMULATORS:
        raise LabError(f"unsupported provider {provider!r} on emulator {emulator!r}")
    return AwsProvider(emulator)  # type: ignore[arg-type]


def provider_for(lab: Lab | None) -> Provider:
    """The provider a lab runs on; without a lab, AWS on Floci."""
    return get_provider(lab.provider, lab.emulator) if lab else get_provider()


__all__ = ["EMULATORS", "AwsProvider", "Provider", "get_provider", "provider_for"]
