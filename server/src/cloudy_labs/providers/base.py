"""What the lab engine needs from a cloud provider backed by a local emulator."""

from typing import Any, Protocol


class Provider(Protocol):
    def client(self, service: str, credentials: tuple[str, str] | None = None) -> Any: ...

    def env(self) -> dict[str, str]:
        """Shell variables that point the provider's CLI at the emulator."""
        ...

    def reset(self) -> None:
        """Wipe all state in this provider's emulator."""
        ...

    def health(self) -> bool: ...
