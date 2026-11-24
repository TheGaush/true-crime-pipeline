"""RULE_09 hedging/graphic labels & RULE_10 dramatization badge (Task 082)."""

from __future__ import annotations

import ast
from pathlib import Path

from agent4_director.rules.rule_09_10_policy import (
    AUDIO_EVIDENCE_CARD,
    RULE_09_GRAPHIC_DISTRESS_LABEL,
    RULE_09_UNHEDGED_NEWS,
    RULE_10_MISSING_BADGE,
    RULE_10_WRONG_LABEL,
    TRANSCRIPT_DRAMATIZATION_BADGE,
    apply_rule_10_dramatization_badges,
    validate_rule_09,
    validate_rule_09_10,
    validate_rule_10,
)

RULE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent4_director"
    / "rules"
    / "rule_09_10_policy.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}

_COURT_FACT = {
    "fact_id": "fact_court",
    "source_type": "court_ruling",
    "hedging_required": 0,
}

_NEWS_FACT = {
    "fact_id": "fact_news",
    "source_type": "news_report",
    "hedging_required": 1,
}


def _scene(
    scene_id: str,
    *,
    narration: str = "The court held that the warrant was valid.",
    cited: list[str] | None = None,
    labels: list[str] | None = None,
    **extra: object,
) -> dict:
    row: dict = {
        "scene_id": scene_id,
        "approved_narration_text": narration,
        "cited_fact_ids_json": cited or ["fact_court"],
        "visual_engine": "CODE_STICKMAN",
    }
    if labels is not None:
        row["on_screen_labels"] = labels
    row.update(extra)
    return row


def _tts_911_card(scene_id: str, *, audio_delivery: str = "TTS", **extra: object) -> dict:
    return _scene(
        scene_id,
        narration="Operator: what is your emergency?",
        cited=["fact_court"],
        visual_engine=AUDIO_EVIDENCE_CARD,
        motif_component="AudioEvidenceCard",
        quote_kind="911",
        audio_delivery=audio_delivery,
        is_verbatim_quote=True,
        **extra,
    )


def test_module_has_no_network_imports() -> None:
    tree = ast.parse(RULE_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in _BANNED_IMPORTS


def test_rule_09_fails_news_report_without_attribution_hedge() -> None:
    scene = _scene(
        "s_news",
        narration="Neighbors said the porch light stayed on all night.",
        cited=["fact_news"],
    )
    result = validate_rule_09([scene], [_COURT_FACT, _NEWS_FACT])
    assert not result.ok
    assert any(v.code == RULE_09_UNHEDGED_NEWS for v in result.violations)


def test_rule_09_passes_news_report_with_attribution_hedge() -> None:
    scene = _scene(
        "s_news_ok",
        narration=(
            "News accounts reported that neighbors said the porch light stayed on all night."
        ),
        cited=["fact_news"],
    )
    result = validate_rule_09([scene], [_NEWS_FACT])
    assert result.ok


def test_rule_09_fails_graphic_distress_on_screen_label() -> None:
    scene = _scene("s_graphic", labels=["GORE_VISIBLE"])
    result = validate_rule_09([scene], [_COURT_FACT])
    assert not result.ok
    assert any(v.code == RULE_09_GRAPHIC_DISTRESS_LABEL for v in result.violations)


def test_rule_10_auto_injects_dramatization_badge_for_tts_911_card() -> None:
    scene = _tts_911_card("911_card")
    fixed, repairs = apply_rule_10_dramatization_badges([scene])
    assert fixed[0]["show_dramatization_badge"] is True
    assert fixed[0]["dramatization_badge_label"] == TRANSCRIPT_DRAMATIZATION_BADGE
    codes = {r.code for r in repairs}
    assert RULE_10_MISSING_BADGE in codes
    assert RULE_10_WRONG_LABEL in codes


def test_rule_10_validate_with_auto_fix_passes_and_records_repairs() -> None:
    scene = _tts_911_card("911_card")
    result = validate_rule_10([scene], auto_fix=True)
    assert result.ok
    assert result.scenes is not None
    assert result.scenes[0]["show_dramatization_badge"] is True
    assert result.scenes[0]["dramatization_badge_label"] == TRANSCRIPT_DRAMATIZATION_BADGE
    assert result.repairs


def test_rule_10_validate_without_auto_fix_flags_missing_badge() -> None:
    scene = _tts_911_card("911_card")
    result = validate_rule_10([scene], auto_fix=False)
    assert not result.ok
    assert any(v.code == RULE_10_MISSING_BADGE for v in result.violations)


def test_rule_10_archival_911_does_not_require_badge() -> None:
    scene = _tts_911_card("archival", audio_delivery="ARCHIVAL_WAV")
    fixed, repairs = apply_rule_10_dramatization_badges([scene])
    assert "show_dramatization_badge" not in fixed[0]
    assert repairs == []


def test_rule_10_already_badged_scene_is_unchanged() -> None:
    scene = _tts_911_card(
        "ok",
        show_dramatization_badge=True,
        dramatization_badge_label=TRANSCRIPT_DRAMATIZATION_BADGE,
    )
    fixed, repairs = apply_rule_10_dramatization_badges([scene])
    assert fixed[0]["show_dramatization_badge"] is True
    assert repairs == []


def test_validate_rule_09_10_combined_policy_pass() -> None:
    scene = _scene(
        "combo",
        narration="News accounts reported that a warrant was filed.",
        cited=["fact_news"],
    )
    card = _tts_911_card("911")
    result = validate_rule_09_10([scene, card], [_NEWS_FACT, _COURT_FACT])
    assert result.ok
    assert result.scenes is not None
    assert result.scenes[1]["dramatization_badge_label"] == TRANSCRIPT_DRAMATIZATION_BADGE