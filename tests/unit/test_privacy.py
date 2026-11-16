from rag.security.privacy import contains_sensitive, redact_mapping, redact_text


def test_telemetry_redaction_masks_pii_and_credential_patterns_recursively() -> None:
    masked = redact_mapping(
        {
            "question": "Contact person@example.test",
            "headers": [{"authorization": "Bearer abcdefghijklmnop"}],
            "api_key": "api_key=super-secret-token-value",
        }
    )
    serialized = str(masked)
    assert "person@example.test" not in serialized
    assert "abcdefghijklmnop" not in serialized
    assert "super-secret-token-value" not in serialized
    assert contains_sensitive("Contact person@example.test")
    assert redact_text("ordinary words") == "ordinary words"
