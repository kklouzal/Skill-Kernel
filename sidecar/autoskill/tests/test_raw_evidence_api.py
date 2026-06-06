import asyncio
import base64
from datetime import UTC, datetime, timedelta

from autoskill.api.app import RawEvidenceIngestRequest, create_app
from autoskill.db.raw_evidence import NullRawEvidenceStore


def test_raw_evidence_ingest_stores_encrypted_metadata_without_returning_ciphertext() -> None:
    store = NullRawEvidenceStore()
    app = create_app(raw_evidence_store=store)
    route = next(route for route in app.routes if route.path == "/v1/ingest/raw-evidence")
    encrypted_payload = {
        "algorithm": "aes-256-gcm",
        "key_id": "plugin-local-raw-spool-v1",
        "iv": base64.b64encode(b"123456789012").decode(),
        "auth_tag": base64.b64encode(b"1234567890123456").decode(),
        "ciphertext": base64.b64encode(b"encrypted private prompt bytes").decode(),
    }

    async def run():
        return await route.endpoint(
            request=RawEvidenceIngestRequest(
                workspace_id="dev-01",
                source_event_hash="sha256:source",
                source_kind="live_hook",
                source_id="llm_input",
                session_id="session-1",
                turn_id="turn-1",
                raw_kind="model_input",
                content_hash="sha256:content",
                sensitivity_level="private",
                taint=["llm"],
                retention_until=datetime.now(UTC) + timedelta(hours=1),
                encryption_key_id="plugin-local-raw-spool-v1",
                encrypted_payload=encrypted_payload,
                capture_policy_id="plugin.raw-capture.v1",
                redaction_policy_id="plugin.secret-mask.v1",
                access_policy={"browser_exposure": "forbidden"},
            ),
            authorization=None,
        )

    response = asyncio.run(run())

    assert len(store.records) == 1
    assert len(store.access_log) == 1
    record = response.record
    assert record["raw_evidence_record_id"]
    assert record["content_hash"] == "sha256:content"
    assert record["content_policy"]["raw_evidence_returned"] is False
    assert "ciphertext" not in record
    assert "encrypted private prompt bytes" not in str(record)
    assert store.access_log[0].purpose == "raw_capture_ingest"
    assert store.access_log[0].exposure_level == "metadata"
