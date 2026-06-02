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


def test_strips_prompt_and_message_content_by_default() -> None:
    payload = {
        "provider": "llama-cpp-compaction",
        "model": "gemma-4-E2B-it-IQ4_NL.gguf",
        "systemPrompt": "private system prompt with sk-abcdefghijklmnopqrstuvwxyz",
        "messages": [
            {"role": "user", "content": "private user message"},
            {"role": "assistant", "content": "private assistant message"},
        ],
    }

    redacted = redact_payload(payload)

    assert redacted["provider"] == "llama-cpp-compaction"
    assert redacted["model"] == "gemma-4-E2B-it-IQ4_NL.gguf"
    assert redacted["systemPrompt"].startswith("[REDACTED_CONTENT bytes=")
    assert redacted["messages"][0]["role"] == "user"
    assert redacted["messages"][0]["content"].startswith("[REDACTED_CONTENT bytes=")
    assert "private user message" not in str(redacted)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in str(redacted)


def test_raw_conversation_capture_still_redacts_secrets() -> None:
    payload = {
        "systemPrompt": "keep body but redact sk-abcdefghijklmnopqrstuvwxyz",
    }

    redacted = redact_payload(payload, capture_raw_conversation=True)

    assert redacted["systemPrompt"] == "keep body but redact [REDACTED]"
