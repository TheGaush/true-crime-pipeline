"""Pure-function tests for the scout policy kill switch."""

from __future__ import annotations

import ast
from pathlib import Path

from agent1_scout.kill_switch import (
    AMBIGUOUS_MINOR,
    CHILD_ABUSE,
    MASS_SHOOTING,
    MINOR_CENTERED,
    MISSING_DISPOSITION,
    PASSED,
    REJECTED,
    TERRORISM,
    UNCONVICTED_SUSPECT,
    PolicyKillSwitchGate,
)

GATE = PolicyKillSwitchGate()
SOURCE = Path(__file__).resolve().parents[1] / "src" / "agent1_scout" / "kill_switch.py"
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}


def _adult_conviction(**overrides: object) -> dict[str, object]:
    candidate: dict[str, object] = {
        "candidate_id": "cand_adult",
        "defendant_name": "Alex Morgan",
        "defendant_age_status": "adult",
        "disposition_status": "STANDING_CONVICTION",
        "conviction_confirmed": True,
        "case_focus": "Adult defendant convicted after a documented trial.",
    }
    candidate.update(overrides)
    return candidate


def _rejected_reason(candidate: dict[str, object]) -> str:
    decision = GATE.evaluate(candidate)
    assert decision.status == REJECTED
    assert decision.rejected is True
    assert decision.passed is False
    assert isinstance(decision.policy_kill_reason, str)
    assert decision.policy_kill_reason
    return decision.policy_kill_reason


def test_rejects_minor_as_victim_witness_or_offender() -> None:
    for role in ("victim", "witness", "offender"):
        candidate = _adult_conviction(
            subjects=[{"role": role, "age_status": "minor"}],
            case_focus=f"The case centers on a minor {role}.",
        )
        assert _rejected_reason(candidate) == MINOR_CENTERED


def test_rejects_mass_shooting() -> None:
    candidate = _adult_conviction(centers_on=["mass_shooting"])
    assert _rejected_reason(candidate) == MASS_SHOOTING


def test_rejects_terrorism() -> None:
    candidate = _adult_conviction(
        case_focus="The case centers on terrorism.",
    )
    assert _rejected_reason(candidate) == TERRORISM


def test_rejects_child_abuse() -> None:
    candidate = _adult_conviction(offense_categories=["child_abuse"])
    assert _rejected_reason(candidate) == CHILD_ABUSE


def test_rejects_unconvicted_suspect() -> None:
    candidate = {
        "suspect_name": "Riley Quinn",
        "suspect_age_status": "adult",
        "disposition_status": "PENDING",
        "conviction_confirmed": False,
        "case_focus": "Adult suspect with no conviction on record.",
    }
    assert _rejected_reason(candidate) == UNCONVICTED_SUSPECT


def test_passes_adult_standing_conviction() -> None:
    decision = GATE.evaluate(_adult_conviction())
    assert decision.status == PASSED
    assert decision.passed is True
    assert decision.rejected is False
    assert decision.policy_kill_reason is None


def test_passes_appellate_review_of_standing_conviction() -> None:
    candidate = _adult_conviction(
        disposition_status="AFFIRMED",
        appellate_review=True,
        case_focus="Appellate court affirmed the conviction of an adult defendant.",
    )
    decision = GATE.evaluate(candidate)
    assert decision.status == PASSED
    assert decision.policy_kill_reason is None


def test_rejects_ambiguous_minor_involvement() -> None:
    candidate = _adult_conviction(
        minor_involvement="ambiguous",
        case_focus="Adult defendant convicted; a bystander's status was not established.",
    )
    assert _rejected_reason(candidate) == AMBIGUOUS_MINOR


def test_rejects_missing_or_blank_disposition() -> None:
    missing = {
        "suspect_name": "Riley Quinn",
        "suspect_age_status": "adult",
        "case_focus": "Suspect named in a filing with no disposition.",
    }
    blank = dict(missing)
    blank["disposition_status"] = "   "
    assert _rejected_reason(missing) == MISSING_DISPOSITION
    assert _rejected_reason(blank) == MISSING_DISPOSITION


def test_minor_count_language_is_not_minor_involvement() -> None:
    candidate = _adult_conviction(
        disposition_status="AFFIRMED",
        appellate_review=True,
        case_focus="The opinion affirmed the murder conviction and reversed one minor count.",
    )
    decision = GATE.evaluate(candidate)
    assert decision.status == PASSED
    assert decision.policy_kill_reason is None


def test_reversed_appeal_does_not_pass() -> None:
    candidate = _adult_conviction(
        disposition_status="REVERSED",
        appellate_review=True,
        case_focus="Appellate court reversed the conviction of an adult defendant.",
    )
    assert _rejected_reason(candidate) == UNCONVICTED_SUSPECT


def test_adult_conviction_does_not_override_a_blocked_category() -> None:
    candidate = _adult_conviction(title="Documentary lead on a mass shooting")
    assert _rejected_reason(candidate) == MASS_SHOOTING


def test_evaluate_is_pure_and_does_not_mutate_input() -> None:
    candidate = _adult_conviction()
    snapshot = dict(candidate)
    first = GATE.evaluate(candidate)
    second = GATE.evaluate(dict(snapshot))
    assert candidate == snapshot
    assert first == second


def test_module_does_not_import_network_libraries() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(_BANNED_IMPORTS)
