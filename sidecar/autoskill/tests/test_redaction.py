from autoskill.core.redaction import redact_payload, redact_text


def test_redacts_secret_values_and_email_addresses() -> None:
    text = "email me at test@example.com with token sk-abcdefghijklmnopqrstuvwxyz"
    redacted = redact_text(text)
    assert "test@example.com" not in redacted
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED]" in redacted


def test_redacts_secret_keys_recursively() -> None:
    payload = {"nested": [{"api_key": "abc"}, {"safe": "hello"}], "Authorization": "Bearer abc"}
    redacted = redact_payload(payload)
    assert redacted["nested"][0]["api_key"] == "[REDACTED]"
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["nested"][1]["safe"] == "hello"

