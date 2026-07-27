"""Conservative redaction for persisted operational error messages."""

import re

_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b(api[-_ ]?key|password|secret|token)(\s*[:=]\s*)([^\s,;]+)"
)
_URL_CREDENTIAL_PATTERN = re.compile(r"(://)[^:/@\s]+:[^@\s]+@")


def redact_error_detail(value: str, *, max_length: int = 1000) -> str:
    """Remove common credentials before an exception message enters durable storage."""

    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    redacted = _CREDENTIAL_PATTERN.sub(r"\1\2[REDACTED]", redacted)
    redacted = _URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]@", redacted)
    return redacted[:max_length]
