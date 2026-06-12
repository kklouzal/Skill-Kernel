import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "autoskill_observatory_live_smoke.py"
SPEC = importlib.util.spec_from_file_location(
    "autoskill_observatory_live_smoke",
    SCRIPT_PATH,
)
assert SPEC is not None
smoke = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(smoke)


def test_observatory_live_smoke_summary_is_content_safe_and_assertable() -> None:
    smoke_id = "observatory-live-smoke-test"
    snapshot_payload = {
        "event_type": "snapshot",
        "seq": 10,
        "cursor_seq": 42,
    }
    live_payload = {
        "event_type": "component_health_changed",
        "seq": 43,
        "cursor_seq": 43,
        "payload": {"health": "degraded", "smoke_id": smoke_id, "phase": "live"},
    }

    smoke._assert_smoke(
        snapshot_event="snapshot",
        snapshot_payload=snapshot_payload,
        stale_seq=42,
        live_event_name="component_health_changed",
        live_payload=live_payload,
        live_seq=43,
        smoke_id=smoke_id,
    )
    summary = smoke._summarize_smoke(
        workspace_id="dev-01",
        smoke_id=smoke_id,
        snapshot_payload=snapshot_payload,
        stale_seq=42,
        live_payload=live_payload,
        live_seq=43,
    )

    assert summary == {
        "schema": "autoskill.observatory-live-smoke.v1",
        "ok": True,
        "workspace_id": "dev-01",
        "smoke_id": smoke_id,
        "snapshot_seq": 10,
        "snapshot_cursor_seq": 42,
        "stale_outbox_seq": 42,
        "live_outbox_seq": 43,
        "live_event_type": "component_health_changed",
        "raw_vault_exposure": False,
        "runtime_skill_writes": False,
        "plugin_activation": False,
        "autonomous_apply": False,
        "live_openclaw_mutation": False,
    }


def test_observatory_live_smoke_asserts_snapshot_cursor_fence() -> None:
    with pytest.raises(SystemExit, match="snapshot cursor did not fence"):
        smoke._assert_smoke(
            snapshot_event="snapshot",
            snapshot_payload={
                "event_type": "snapshot",
                "seq": 10,
                "cursor_seq": 41,
            },
            stale_seq=42,
            live_event_name="component_health_changed",
            live_payload={
                "event_type": "component_health_changed",
                "seq": 43,
                "cursor_seq": 43,
                "payload": {
                    "smoke_id": "observatory-live-smoke-test",
                    "phase": "live",
                },
            },
            live_seq=43,
            smoke_id="observatory-live-smoke-test",
        )
