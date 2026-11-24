"""Tests for fail-closed compliance audit receipt writer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent3_gatekeeper.audit_writer import (
    COMPLIANCE_BLOCKED,
    COMPLIANCE_PASSED,
    EPISODE_POST_COMPLIANCE,
    EPISODE_PRE_COMPLIANCE,
    FoiaAssetRecord,
    PolicyGateSnapshot,
    evaluate_compliance,
    evaluate_foia_asset,
    write_compliance_audit_receipt,
)

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schema"
PIPELINE_SQL = (SCHEMA_DIR / "pipeline.sql").read_text(encoding="utf-8")

PASSED_GATES = PolicyGateSnapshot(
    provenance_whitelist_ok=1,
    that_vs_how_passed=1,
    anti_legal_persona_passed=1,
    first_30s_adsense_safe=1,
    altered_content_disclosure=1,
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(PIPELINE_SQL)
    return conn


def _seed_case_episode(conn: sqlite3.Connection) -> tuple[str, str]:
    case_id = "case_1"
    episode_id = "ep_1"
    conn.execute(
        """INSERT INTO cases (
             case_id, defendant_name, incident_year, jurisdiction, docket_id,
             primary_record_verified, verification_source, disposition_status,
             conviction_confirmed, anonymization_status, anonymized_by, anonymized_at,
             anonymization_artifact_sha256, created_at, updated_at
           ) VALUES (
             ?, 'Jordan Hale', 2019, 'Marlow County, Montana', '2019-CR-1042', 1,
             'Montana Supreme Court opinion fixture', 'AFFIRMED', 1, 'APPROVED',
             'reviewer_compliance', 1795392000,
             '8c8167c954d82b3e11b4239eb1683b5e44e99dd992b8eabf37a092a5a721a6de',
             1795300000, 1795392000
           )""",
        (case_id,),
    )
    conn.execute(
        """INSERT INTO episodes (
             episode_id, case_id, state, flow_backend_mode, cold_open_archetype,
             total_master_ms, timeline_validated_sha256, ready_bundle_sha256,
             updated_at, created_at
           ) VALUES (
             ?, ?, ?, 'GEMINI_OMNI_INTERACTIONS', '911_CALL_IN_MEDIA_RES',
             1200000, 'sha_tl', 'sha_bundle', 1795392000, 1795300000
           )""",
        (episode_id, case_id, EPISODE_PRE_COMPLIANCE),
    )
    return case_id, episode_id


def _insert_foia(
    conn: sqlite3.Connection,
    *,
    asset_id: str,
    case_id: str,
    media_kind: str = "bodycam_mp4",
    normalized: int = 1,
    spoken_pii_bleeped: int = 1,
    asr_disagreement: float = 0.0,
    human_audio_review_required: int = 0,
    demucs_applied: int = 0,
    rights_status: str = "APPROVED",
    watermark_clean: int = 1,
    visual_pii_blurred: int = 1,
) -> None:
    conn.execute(
        """INSERT INTO foia_media_assets (
             asset_id, case_id, source_domain, source_url, creator_entity, rights_holder,
             license_basis, rights_review_status, rights_reviewed_by, rights_reviewed_at,
             media_kind, raw_path, normalized_cfr_30fps_48k, watermark_clean,
             visual_pii_blurred, spoken_pii_bleeped, asr_hypothesis_disagreement,
             human_audio_review_required, demucs_applied
           ) VALUES (
             ?, ?, 'records.example', 'https://records.example/foia', 'Sheriff Dept',
             'County', 'STATE_PUBLIC_RECORD_PERMITTED', ?, 'rights_reviewer', 1795392000,
             ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        (
            asset_id,
            case_id,
            rights_status,
            media_kind,
            f"media/{asset_id}",
            normalized,
            watermark_clean,
            visual_pii_blurred,
            spoken_pii_bleeped,
            asr_disagreement,
            human_audio_review_required,
            demucs_applied,
        ),
    )


def _compliant_asset(asset_id: str = "fa_bodycam", **kwargs) -> FoiaAssetRecord:
    defaults = dict(
        asset_id=asset_id,
        case_id="case_1",
        media_kind="bodycam_mp4",
        normalized_cfr_30fps_48k=1,
        rights_review_status="APPROVED",
        watermark_clean=1,
        visual_pii_blurred=1,
        spoken_pii_bleeped=1,
        asr_hypothesis_disagreement=0.0,
        human_audio_review_required=0,
        demucs_applied=0,
    )
    defaults.update(kwargs)
    return FoiaAssetRecord(**defaults)


def test_complete_foia_set_passes_and_writes_receipt() -> None:
    conn = _connect()
    case_id, episode_id = _seed_case_episode(conn)
    _insert_foia(conn, asset_id="fa_911", case_id=case_id, media_kind="call_911_wav")
    _insert_foia(conn, asset_id="fa_cam", case_id=case_id, media_kind="bodycam_mp4")

    result = write_compliance_audit_receipt(
        conn,
        case_id=case_id,
        episode_id=episode_id,
        policy_gates=PASSED_GATES,
        audited_at=1795392000,
        audit_id="case_1_audit_fixture",
    )

    assert result.outcome == COMPLIANCE_PASSED
    assert result.episode_state == EPISODE_POST_COMPLIANCE
    assert result.compliance_audit is not None
    assert result.compliance_audit["spoken_pii_audit_passed"] == 1
    assert result.compliance_audit["first_30s_adsense_safe"] == 1

    ep_state = conn.execute(
        "SELECT state FROM episodes WHERE episode_id = ?", (episode_id,)
    ).fetchone()["state"]
    assert ep_state == EPISODE_POST_COMPLIANCE

    audit_count = conn.execute(
        "SELECT COUNT(*) AS c FROM compliance_audits WHERE case_id = ?", (case_id,)
    ).fetchone()["c"]
    assert audit_count == 1

    assert result.compliance_cleared_case is not None
    assert result.compliance_cleared_case["first_30s_adsense_safe"] is True
    assert result.compliance_cleared_case["spoken_pii_audit_passed"] is True


def test_911_wav_missing_spoken_pii_bleeped_is_hard_blocked() -> None:
    asset = _compliant_asset(
        asset_id="fa_911_bad",
        media_kind="call_911_wav",
        spoken_pii_bleeped=0,
    )
    violations = evaluate_foia_asset(asset)
    codes = {v.code for v in violations}
    assert "SPOKEN_PII_911_WAV_BLOCKED" in codes
    assert "SPOKEN_PII_NOT_BLEEPED" in codes

    evaluation = evaluate_compliance(
        case_id="case_1",
        assets=[asset],
        policy_gates=PASSED_GATES,
    )
    assert evaluation.outcome == COMPLIANCE_BLOCKED


def test_911_wav_missing_spoken_pii_blocks_persist() -> None:
    conn = _connect()
    case_id, episode_id = _seed_case_episode(conn)
    _insert_foia(
        conn,
        asset_id="fa_911",
        case_id=case_id,
        media_kind="call_911_wav",
        spoken_pii_bleeped=0,
    )

    result = write_compliance_audit_receipt(
        conn,
        case_id=case_id,
        episode_id=episode_id,
        policy_gates=PASSED_GATES,
        audited_at=1795392000,
    )

    assert result.outcome == COMPLIANCE_BLOCKED
    ep_state = conn.execute(
        "SELECT state FROM episodes WHERE episode_id = ?", (episode_id,)
    ).fetchone()["state"]
    assert ep_state == EPISODE_PRE_COMPLIANCE
    assert (
        conn.execute("SELECT COUNT(*) AS c FROM compliance_audits").fetchone()["c"] == 0
    )


def test_high_asr_disagreement_blocks_without_signoff() -> None:
    asset = _compliant_asset(
        asr_hypothesis_disagreement=0.14,
        human_audio_review_required=1,
        demucs_applied=1,
    )
    evaluation = evaluate_compliance(
        case_id="case_1",
        assets=[asset],
        policy_gates=PASSED_GATES,
    )
    assert evaluation.outcome == COMPLIANCE_BLOCKED
    assert any(v.code == "AUDIO_INTELLIGIBILITY_BLOCKED" for v in evaluation.violations)


def test_high_asr_disagreement_passes_with_human_signoff() -> None:
    asset = _compliant_asset(
        asset_id="fa_demucs",
        asr_hypothesis_disagreement=0.14,
        human_audio_review_required=1,
        demucs_applied=1,
    )
    evaluation = evaluate_compliance(
        case_id="case_1",
        assets=[asset],
        policy_gates=PASSED_GATES,
        human_audio_review_signoffs=frozenset({"fa_demucs"}),
    )
    assert evaluation.outcome == COMPLIANCE_PASSED


def test_policy_gate_fail_closed() -> None:
    asset = _compliant_asset()
    gates = PolicyGateSnapshot(
        provenance_whitelist_ok=1,
        that_vs_how_passed=1,
        anti_legal_persona_passed=1,
        first_30s_adsense_safe=0,
        altered_content_disclosure=1,
    )
    evaluation = evaluate_compliance(
        case_id="case_1",
        assets=[asset],
        policy_gates=gates,
    )
    assert evaluation.outcome == COMPLIANCE_BLOCKED
    assert any(v.code == "POLICY_GATE_BLOCKED" for v in evaluation.violations)


def test_missing_normalized_cfr_blocks() -> None:
    asset = _compliant_asset(normalized_cfr_30fps_48k=0)
    violations = evaluate_foia_asset(asset)
    assert any(v.code == "NORMALIZED_CFR_48K_REQUIRED" for v in violations)