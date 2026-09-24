"""Independent public format versions and strict compatibility guards."""

from __future__ import annotations

from typing import Final

from .errors import ValidationError


PIPELINE_CONTRACT_VERSION: Final = "1"
RUN_MANIFEST_SCHEMA_VERSION: Final = "1"
ARTIFACT_SCHEMA_VERSION: Final = "1"
ADAPTER_MANIFEST_VERSION: Final = 1


def require_supported_version(kind: str, value: object, supported: str | int) -> None:
    """Reject unknown versions without rewriting or silently migrating data."""

    if value != supported:
        raise ValidationError(
            f"{kind} version is unsupported.",
            hint=f"Use a Specromancy release that supports {kind} version {value!r}.",
            details={"observed": value, "supported": supported},
        )
