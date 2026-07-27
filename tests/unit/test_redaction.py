from gamecrafter.security.redaction import redact_error_detail


def test_operational_errors_are_redacted_before_persistence() -> None:
    detail = (
        "authorization=Bearer super-secret "
        "api_key=sk-private "
        "postgresql://user:password@localhost/database"
    )

    redacted = redact_error_detail(detail)

    assert "super-secret" not in redacted
    assert "sk-private" not in redacted
    assert "user:password" not in redacted
    assert redacted.count("[REDACTED]") == 3
