#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "sidecar/autoskill/observatory/fixtures/visual-regression-fixtures.json"
REQUIRED_VISUAL_STATES = {
    "healthy",
    "degraded",
    "blocked",
    "security",
    "regression",
    "context_pressure",
    "freeze",
    "historical_bootstrap",
    "stale_telemetry",
    "reduced_motion",
    "low_power",
    "webgl_fallback",
    "high_load_soak",
}


@dataclass(frozen=True)
class ObservatoryFixture:
    scenario_id: str
    title: str
    expected_health: str
    reason_codes: tuple[str, ...]
    viewport: dict[str, int]
    operator_modes: dict[str, bool]
    load_profile: dict[str, int]
    e2e_journey: tuple[str, ...]
    visual_assertions: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "expected_health": self.expected_health,
            "reason_codes": list(self.reason_codes),
            "viewport": self.viewport,
            "operator_modes": self.operator_modes,
            "load_profile": self.load_profile,
            "e2e_journey": list(self.e2e_journey),
            "visual_assertions": list(self.visual_assertions),
        }


FIXTURES: tuple[ObservatoryFixture, ...] = (
    ObservatoryFixture(
        "healthy",
        "Nominal control-room overview",
        "healthy",
        (),
        {"width": 1440, "height": 920},
        {"reduced_motion": False, "low_power": False, "webgl_available": True},
        {"agents": 3, "transcript_months": 1, "skills": 64, "historical_imports": 2},
        ("/admin/?view=overview", "/admin/?view=workcells", "/admin/?view=cockpit"),
        (
            "all stations render custom cards",
            "semantic edges remain labeled",
            "issue board is empty or low-priority only",
        ),
    ),
    ObservatoryFixture(
        "degraded",
        "Degraded queue and telemetry pressure",
        "degraded",
        ("failed-jobs-present", "read-model-stale"),
        {"width": 1440, "height": 920},
        {"reduced_motion": False, "low_power": False, "webgl_available": True},
        {"agents": 5, "transcript_months": 2, "skills": 128, "historical_imports": 4},
        ("/admin/?view=overview", "/admin/?view=workcells&subsystem=control_storage"),
        ("degraded badges are visible", "workcell bottleneck metrics remain legible"),
    ),
    ObservatoryFixture(
        "blocked",
        "Blocked activation and mutation gate",
        "blocked",
        ("activation-gate-blocked", "scanner-blocking-finding"),
        {"width": 1280, "height": 860},
        {"reduced_motion": False, "low_power": False, "webgl_available": True},
        {"agents": 4, "transcript_months": 2, "skills": 96, "historical_imports": 3},
        ("/admin/?view=cockpit&station=scanner_security", "/admin/?view=trace"),
        ("blocked halo outranks degraded styling", "supporting records stay redacted"),
    ),
    ObservatoryFixture(
        "security",
        "Security and raw-content guardrail",
        "blocked",
        ("raw-content-denied", "csrf-required", "audit-chain-warning"),
        {"width": 1366, "height": 900},
        {"reduced_motion": False, "low_power": False, "webgl_available": True},
        {"agents": 3, "transcript_months": 1, "skills": 80, "historical_imports": 2},
        ("/admin/?view=admin", "/admin/?view=cockpit&station=operator_action_gateway"),
        ("action dialog is modal", "raw-content controls remain audited"),
    ),
    ObservatoryFixture(
        "context_pressure",
        "Context token pressure and ignored-load state",
        "degraded",
        ("context-token-pressure", "ignored-skill-load"),
        {"width": 1440, "height": 920},
        {"reduced_motion": False, "low_power": False, "webgl_available": True},
        {"agents": 6, "transcript_months": 3, "skills": 220, "historical_imports": 6},
        ("/admin/?view=skills", "/admin/?view=cockpit&station=context_compiler"),
        ("token budget panels show pressure", "skill detail keeps budget evidence visible"),
    ),
    ObservatoryFixture(
        "regression",
        "Regression and failed probe diagnostics",
        "blocked",
        ("regression-gate-failed", "probe-bank-regression"),
        {"width": 1440, "height": 920},
        {"reduced_motion": False, "low_power": False, "webgl_available": True},
        {"agents": 4, "transcript_months": 2, "skills": 118, "historical_imports": 3},
        ("/admin/?view=cockpit&station=evaluator_probes", "/admin/?view=trace"),
        (
            "regression gate failure outranks routine degraded state",
            "failed probe evidence links remain content-safe",
        ),
    ),
    ObservatoryFixture(
        "freeze",
        "Frozen skill with rollback evidence",
        "frozen",
        ("canary-critical-failure", "rollback-queued"),
        {"width": 1440, "height": 920},
        {"reduced_motion": False, "low_power": False, "webgl_available": True},
        {"agents": 4, "transcript_months": 2, "skills": 120, "historical_imports": 3},
        ("/admin/?view=cockpit&station=canary_rollback", "/admin/?view=trace"),
        ("freeze state is visually distinct", "rollback links preserve object refs"),
    ),
    ObservatoryFixture(
        "historical_bootstrap",
        "Historical bootstrap import and candidate review",
        "degraded",
        ("historical-bootstrap-active", "tainted-historical-evidence"),
        {"width": 1440, "height": 920},
        {"reduced_motion": False, "low_power": False, "webgl_available": True},
        {"agents": 6, "transcript_months": 9, "skills": 180, "historical_imports": 12},
        (
            "/admin/?view=workcells&subsystem=capture_bootstrap",
            "/admin/?view=cockpit&station=historical_ingestion",
        ),
        (
            "historical import progress and taint confidence are visible",
            "bootstrap candidates remain propose-only with source lineage",
        ),
    ),
    ObservatoryFixture(
        "stale_telemetry",
        "Stale live stream and partial telemetry",
        "unknown",
        ("telemetry-stale", "missing-required-signal"),
        {"width": 1280, "height": 860},
        {"reduced_motion": False, "low_power": False, "webgl_available": True},
        {"agents": 4, "transcript_months": 2, "skills": 100, "historical_imports": 4},
        ("/admin/?view=overview", "/admin/?view=admin"),
        ("green health is not shown for missing signals", "freshness badges are visible"),
    ),
    ObservatoryFixture(
        "reduced_motion",
        "Reduced-motion operator mode",
        "degraded",
        ("reduced-motion-enabled",),
        {"width": 1024, "height": 768},
        {"reduced_motion": True, "low_power": False, "webgl_available": True},
        {"agents": 3, "transcript_months": 1, "skills": 90, "historical_imports": 2},
        ("/admin/?view=overview", "/admin/?view=trace"),
        ("particle layer is disabled", "station and edge information remains complete"),
    ),
    ObservatoryFixture(
        "low_power",
        "Low-power dense dashboard mode",
        "degraded",
        ("low-power-mode",),
        {"width": 390, "height": 844},
        {"reduced_motion": True, "low_power": True, "webgl_available": False},
        {"agents": 2, "transcript_months": 1, "skills": 72, "historical_imports": 1},
        ("/admin/?view=overview", "/admin/?view=workcells"),
        ("mobile layout does not overlap controls", "charts collapse below the graph"),
    ),
    ObservatoryFixture(
        "webgl_fallback",
        "WebGL unavailable visual fallback",
        "healthy",
        ("webgl-unavailable",),
        {"width": 1366, "height": 900},
        {"reduced_motion": False, "low_power": False, "webgl_available": False},
        {"agents": 3, "transcript_months": 1, "skills": 64, "historical_imports": 2},
        ("/admin/?view=overview",),
        ("graph remains the source of truth", "data-backed effects are optional"),
    ),
    ObservatoryFixture(
        "high_load_soak",
        "High-load soak history",
        "degraded",
        ("storage-growth-watch", "read-model-backpressure"),
        {"width": 1920, "height": 1080},
        {"reduced_motion": False, "low_power": False, "webgl_available": True},
        {
            "agents": 24,
            "transcript_months": 18,
            "skills": 1600,
            "historical_imports": 48,
            "live_events": 250000,
        },
        ("/admin/?view=overview", "/admin/?view=skills", "/admin/?view=trace"),
        (
            "bounded collection limits prevent unbounded fetches",
            "overview remains useful with large skill libraries",
            "trace replay list remains paginated",
        ),
    ),
)


def build_fixture_report() -> dict[str, Any]:
    fixtures = [fixture.to_json() for fixture in FIXTURES]
    scenario_ids = {fixture["scenario_id"] for fixture in fixtures}
    validation_errors = validate_fixture_report(fixtures)
    return {
        "schema": "autoskill.observatory-fixtures.v1",
        "ready": not validation_errors,
        "summary": {
            "scenario_count": len(fixtures),
            "required_visual_states": len(REQUIRED_VISUAL_STATES),
            "missing_visual_states": sorted(REQUIRED_VISUAL_STATES - scenario_ids),
            "high_load_skill_count": _high_load_fixture(fixtures)["load_profile"]["skills"],
            "validation_errors": validation_errors,
        },
        "fixtures": fixtures,
    }


def validate_fixture_report(fixtures: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    scenario_ids = {str(fixture.get("scenario_id")) for fixture in fixtures}
    missing = REQUIRED_VISUAL_STATES - scenario_ids
    if missing:
        errors.append(f"missing visual states: {', '.join(sorted(missing))}")
    for fixture in fixtures:
        scenario_id = str(fixture.get("scenario_id"))
        if not fixture.get("e2e_journey"):
            errors.append(f"{scenario_id} has no e2e journey")
        if not fixture.get("visual_assertions"):
            errors.append(f"{scenario_id} has no visual assertions")
        if "viewport" not in fixture:
            errors.append(f"{scenario_id} has no viewport")
    high_load = _high_load_fixture(fixtures)
    load = high_load["load_profile"]
    if load["transcript_months"] < 12 or load["skills"] < 1000 or load["agents"] < 12:
        errors.append("high_load_soak fixture does not meet large-deployment thresholds")
    return errors


def _high_load_fixture(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    for fixture in fixtures:
        if fixture["scenario_id"] == "high_load_soak":
            return fixture
    return {"load_profile": {"transcript_months": 0, "skills": 0, "agents": 0}}


def render_json() -> str:
    return json.dumps(build_fixture_report(), indent=2, sort_keys=True) + "\n"


def write_fixture(*, check: bool = False) -> int:
    rendered = render_json()
    if check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != rendered:
            print(f"{OUTPUT_PATH} is stale; rerun {Path(__file__).name}", file=sys.stderr)
            return 1
        return 0
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit or refresh deterministic Observatory E2E/load/visual fixtures.",
    )
    parser.add_argument("--check", action="store_true", help="Fail if the fixture file is stale.")
    parser.add_argument("--write", action="store_true", help="Write the checked-in fixture file.")
    parser.add_argument("--json", action="store_true", help="Emit the fixture report JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        return write_fixture(check=True)
    if args.write:
        return write_fixture(check=False)
    if args.json:
        print(render_json(), end="")
        return 0 if build_fixture_report()["ready"] else 1
    print(render_json(), end="")
    return 0 if build_fixture_report()["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
