"""Secret redaction and deterministic UTF-8 size limiting."""

from __future__ import annotations

import re
from typing import Final


REDACTED: Final = "[REDACTED]"
TRUNCATION_MARKER: Final = "\n[output truncated by specromancy]\n"

_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|secret)\s*([:=])\s*([^\s,;]+)"
)
_AUTHORIZATION = re.compile(
    r"(?i)\b(authorization\s*:\s*(?:bearer|basic)|bearer)\s+[^\s,;]+"
)
_KNOWN_TOKEN = re.compile(
    r"\b(?:ghp|gho|ghu|ghs|github_pat|sk|xox[abprs])[-_][A-Za-z0-9_-]{10,}\b"
)
_AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----.*?"
    r"-----END(?: [A-Z0-9]+)* PRIVATE KEY-----",
    re.DOTALL,
)


def redact_text(value: str) -> str:
    """Replace common credential forms without exposing matched values."""

    redacted = _PRIVATE_KEY.sub(REDACTED, value)
    redacted = _ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", redacted
    )
    redacted = _AUTHORIZATION.sub(
        lambda match: f"{match.group(1)} {REDACTED}", redacted
    )
    redacted = _KNOWN_TOKEN.sub(REDACTED, redacted)
    redacted = _AWS_KEY.sub(REDACTED, redacted)
    redacted = _JWT.sub(REDACTED, redacted)
    return redacted


def contains_secret(value: str) -> bool:
    """Return whether redaction would alter a value."""

    return redact_text(value) != value


def bounded_utf8(
    value: str,
    limit: int,
    *,
    marker: str = TRUNCATION_MARKER,
) -> tuple[str, bool]:
    """Bound text by encoded bytes while never returning invalid UTF-8."""

    if limit < 0:
        raise ValueError("limit must be non-negative")
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return value, False
    marker_bytes = marker.encode("utf-8")
    if len(marker_bytes) > limit:
        return marker_bytes[:limit].decode("utf-8", errors="ignore"), True
    available = limit - len(marker_bytes)
    prefix = encoded[:available].decode("utf-8", errors="ignore")
    return prefix + marker, True


def redact_and_bound(value: str, limit: int) -> tuple[str, bool]:
    """Redact before truncating so discarded boundaries cannot expose secrets."""

    return bounded_utf8(redact_text(value), limit)

