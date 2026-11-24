"""Fail-closed compliance audit receipt writer for Agent 3 FOIA clearance."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

ASR_DISAGREEMENT_THRESHOLD = 0.10

COMPLIANCE_PASSED = "COMPLIANCE_PASSED"
COMPLIANCE_BLOCKED = "COMPLIANCE_BLOCKED"

EPISODE_PRE_COMPLIANCE = "EVIDENCE_AND_2K_LOCKED"
EPISODE_POST_COMPLIANCE = "COMPLIANCE_PASSED"

_MEDIA_KIND_911 = "call_911_wav"


@dataclass(frozen=True, slots=True)
class FoiaAssetRecord:
    asset_id: str
    case_id: str
    media_kind: str
    normalized_cfr_30fps_48k: int
    rights_review_status: str
    watermark_clean: int
    visual_pii_blurred: int
    spoken_pii_bleeped: int
    asr_hypothesis_disagreement: float
    human_audio_review_required: int
    demucs_applied: int = 0


@dataclass(frozen=True, slots=True)
class PolicyGateSnapshot:
    """Upstream Agent 3 policy linters (Tasks 045–057) summarized as receipt flags."""

    provenance_whitelist_ok: int
    that_vs_how_passed: int
    anti_legal_persona_passed: int
    first_30s_adsense_safe: int
    altered_content_disclosure: int


@dataclass(frozen=True, slots=True)
class ComplianceViolation:
    code: str
    detail: str
    asset_id: str | None = None


@dataclass(frozen=True, slots=True)
class ComplianceAuditOutcome:
    outcome: str
    violations: tuple[ComplianceViolation, ...]
    audit_id: str | None = None
    compliance_audit: dict[str, Any] | None = None
    compliance_cleared_case: dict[str, Any] | None = None
    episode_state: str | None = None


_FOIA_SELECT = """
SELECT
  asset_id,
  case_id,
  media_kind,
  normalized_cfr_30fps_48k,
  rights_review_status,
  watermark_clean,
  visual_pii_blurred,
  spoken_pii_bleeped,
  asr_hypothesis_disagreement,
  human_audio_review_required,
  demucs_applied
FROM foia_media_assets
WHERE case_id = ?
ORDER BY asset_id
"""


def foia_asset_from_row(row: Mapping[str, Any]) -> FoiaAssetRecord:
    return FoiaAssetRecord(
        asset_id=str(row["asset_id"]),
        case_id=str(row["case_id"]),
        media_kind=str(row["media_kind"]),
        normalized_cfr_30fps_48k=int(row["normalized_cfr_30fps_48k"]),
        rights_review_status=str(row["rights_review_status"]),
        watermark_clean=int(row["watermark_clean"]),
        visual_pii_blurred=int(row["visual_pii_blurred"]),
        spoken_pii_bleeped=int(row["spoken_pii_bleeped"]),
        asr_hypothesis_disagreement=float(row["asr_hypothesis_disagreement"]),
        human_audio_review_required=int(row["human_audio_review_required"]),
        demucs_applied=int(row["demucs_applied"]),
    )


def load_foia_assets_for_case(conn: sqlite3.Connection, case_id: str) -> list[FoiaAssetRecord]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(_FOIA_SELECT, (case_id,)).fetchall()
    return [foia_asset_from_row(row) for row in rows]


def _audio_intelligibility_ok(
    asset: FoiaAssetRecord,
    human_audio_review_signoffs: frozenset[str],
) -> bool:
    if asset.asr_hypothesis_disagreement <= ASR_DISAGREEMENT_THRESHOLD:
        return True
    if asset.asset_id in human_audio_review_signoffs:
        return True
    return False


def evaluate_foia_asset(
    asset: FoiaAssetRecord,
    *,
    human_audio_review_signoffs: frozenset[str] | None = None,
) -> list[ComplianceViolation]:
    """Return per-asset violations; empty list means the asset is cleared."""
    signoffs = human_audio_review_signoffs or frozenset()
    violations: list[ComplianceViolation] = []

    checks: tuple[tuple[str, bool, str], ...] = (
        (
            "NORMALIZED_CFR_48K_REQUIRED",
            asset.normalized_cfr_30fps_48k == 1,
            "normalized_cfr_30fps_48k must be 1",
        ),
        (
            "RIGHTS_NOT_APPROVED",
            asset.rights_review_status == "APPROVED",
            f"rights_review_status must be APPROVED (got {asset.rights_review_status!r})",
        ),
        (
            "WATERMARK_NOT_CLEAN",
            asset.watermark_clean == 1,
            "watermark_clean must be 1",
        ),
        (
            "VISUAL_PII_NOT_BLURRED",
            asset.visual_pii_blurred == 1,
            "visual_pii_blurred must be 1",
        ),
        (
            "SPOKEN_PII_NOT_BLEEPED",
            asset.spoken_pii_bleeped == 1,
            "spoken_pii_bleeped must be 1",
        ),
    )

    for code, ok, detail in checks:
        if not ok:
            violations.append(
                ComplianceViolation(code=code, detail=detail, asset_id=asset.asset_id)
            )

    if asset.media_kind == _MEDIA_KIND_911 and asset.spoken_pii_bleeped != 1:
        violations.append(
            ComplianceViolation(
                code="SPOKEN_PII_911_WAV_BLOCKED",
                detail="911 WAV missing spoken_pii_bleeped=1 hard-blocks compliance",
                asset_id=asset.asset_id,
            )
        )

    if not _audio_intelligibility_ok(asset, signoffs):
        detail = (
            f"asr_hypothesis_disagreement {asset.asr_hypothesis_disagreement:.4f} "
            f"exceeds {ASR_DISAGREEMENT_THRESHOLD} without human audio review sign-off"
        )
        if asset.human_audio_review_required == 1:
            detail += " (human_audio_review_required=1)"
        violations.append(
            ComplianceViolation(
                code="AUDIO_INTELLIGIBILITY_BLOCKED",
                detail=detail,
                asset_id=asset.asset_id,
            )
        )

    return violations


def evaluate_policy_gates(snapshot: PolicyGateSnapshot) -> list[ComplianceViolation]:
    violations: list[ComplianceViolation] = []
    gate_fields: tuple[tuple[str, int], ...] = (
        ("provenance_whitelist_ok", snapshot.provenance_whitelist_ok),
        ("that_vs_how_passed", snapshot.that_vs_how_passed),
        ("anti_legal_persona_passed", snapshot.anti_legal_persona_passed),
        ("first_30s_adsense_safe", snapshot.first_30s_adsense_safe),
    )
    for field_name, value in gate_fields:
        if value != 1:
            violations.append(
                ComplianceViolation(
                    code="POLICY_GATE_BLOCKED",
                    detail=f"{field_name} must be 1 (fail-closed)",
                )
            )
    return violations


def evaluate_compliance(
    *,
    case_id: str,
    assets: Sequence[FoiaAssetRecord],
    policy_gates: PolicyGateSnapshot,
    human_audio_review_signoffs: frozenset[str] | None = None,
) -> ComplianceAuditOutcome:
    """Pure evaluation: no SQLite writes."""
    signoffs = human_audio_review_signoffs or frozenset()
    violations: list[ComplianceViolation] = list(evaluate_policy_gates(policy_gates))

    if not assets:
        violations.append(
            ComplianceViolation(
                code="NO_FOIA_ASSETS",
                detail=f"case {case_id!r} has no foia_media_assets to audit",
            )
        )
    else:
        for asset in assets:
            if asset.case_id != case_id:
                violations.append(
                    ComplianceViolation(
                        code="CASE_ASSET_MISMATCH",
                        detail=f"asset {asset.asset_id!r} belongs to {asset.case_id!r}, not {case_id!r}",
                        asset_id=asset.asset_id,
                    )
                )
                continue
            violations.extend(
                evaluate_foia_asset(asset, human_audio_review_signoffs=signoffs)
            )

    if violations:
        return ComplianceAuditOutcome(
            outcome=COMPLIANCE_BLOCKED,
            violations=tuple(violations),
        )

    spoken_pii_audit_passed = 1
    return ComplianceAuditOutcome(
        outcome=COMPLIANCE_PASSED,
        violations=(),
        compliance_audit={
            "case_id": case_id,
            "provenance_whitelist_ok": 1,
            "that_vs_how_passed": 1,
            "anti_legal_persona_passed": 1,
            "first_30s_adsense_safe": 1,
            "spoken_pii_audit_passed": spoken_pii_audit_passed,
            "altered_content_disclosure": policy_gates.altered_content_disclosure,
        },
    )


def build_compliance_cleared_case(
    case_row: Mapping[str, Any],
    audit_row: Mapping[str, Any],
) -> dict[str, Any]:
    """Shape ``ComplianceClearedCase`` contract fields from SQLite rows."""
    return {
        "case_id": case_row["case_id"],
        "defendant_name": case_row["defendant_name"],
        "incident_year": case_row["incident_year"],
        "jurisdiction": case_row["jurisdiction"],
        "verification_source": case_row["verification_source"],
        "disposition_status": case_row["disposition_status"],
        "conviction_confirmed": bool(case_row["conviction_confirmed"]),
        "primary_record_verified": bool(case_row["primary_record_verified"]),
        "anonymization_status": case_row["anonymization_status"],
        "anonymized_by": case_row["anonymized_by"],
        "anonymized_at": case_row["anonymized_at"],
        "anonymization_artifact_sha256": case_row["anonymization_artifact_sha256"],
        "audit_id": audit_row["audit_id"],
        "provenance_whitelist_ok": bool(audit_row["provenance_whitelist_ok"]),
        "that_vs_how_passed": bool(audit_row["that_vs_how_passed"]),
        "anti_legal_persona_passed": bool(audit_row["anti_legal_persona_passed"]),
        "first_30s_adsense_safe": bool(audit_row["first_30s_adsense_safe"]),
        "spoken_pii_audit_passed": bool(audit_row["spoken_pii_audit_passed"]),
        "altered_content_disclosure": bool(audit_row["altered_content_disclosure"]),
        "audited_at": audit_row["audited_at"],
    }


def write_compliance_audit_receipt(
    conn: sqlite3.Connection,
    *,
    case_id: str,
    episode_id: str,
    policy_gates: PolicyGateSnapshot,
    human_audio_review_signoffs: frozenset[str] | None = None,
    audited_at: int,
    audit_id: str | None = None,
) -> ComplianceAuditOutcome:
    """Evaluate FOIA assets, persist ``compliance_audits``, advance episode on pass."""
    conn.row_factory = sqlite3.Row
    assets = load_foia_assets_for_case(conn, case_id)
    evaluation = evaluate_compliance(
        case_id=case_id,
        assets=assets,
        policy_gates=policy_gates,
        human_audio_review_signoffs=human_audio_review_signoffs,
    )
    if evaluation.outcome == COMPLIANCE_BLOCKED:
        return evaluation

    ep_row = conn.execute(
        "SELECT episode_id, case_id, state FROM episodes WHERE episode_id = ?",
        (episode_id,),
    ).fetchone()
    if ep_row is None:
        return ComplianceAuditOutcome(
            outcome=COMPLIANCE_BLOCKED,
            violations=(
                ComplianceViolation(
                    code="EPISODE_NOT_FOUND",
                    detail=f"episode {episode_id!r} does not exist",
                ),
            ),
        )
    if ep_row["case_id"] != case_id:
        return ComplianceAuditOutcome(
            outcome=COMPLIANCE_BLOCKED,
            violations=(
                ComplianceViolation(
                    code="EPISODE_CASE_MISMATCH",
                    detail=f"episode {episode_id!r} is not owned by case {case_id!r}",
                ),
            ),
        )
    if ep_row["state"] != EPISODE_PRE_COMPLIANCE:
        return ComplianceAuditOutcome(
            outcome=COMPLIANCE_BLOCKED,
            violations=(
                ComplianceViolation(
                    code="EPISODE_STATE_INVALID",
                    detail=(
                        f"episode must be {EPISODE_PRE_COMPLIANCE!r} "
                        f"(got {ep_row['state']!r})"
                    ),
                ),
            ),
        )

    resolved_audit_id = audit_id or f"{case_id}_audit_{uuid.uuid4().hex[:12]}"
    audit_payload = evaluation.compliance_audit or {}
    conn.execute(
        """INSERT INTO compliance_audits (
             audit_id, case_id, provenance_whitelist_ok, that_vs_how_passed,
             anti_legal_persona_passed, first_30s_adsense_safe, spoken_pii_audit_passed,
             altered_content_disclosure, audited_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            resolved_audit_id,
            case_id,
            audit_payload["provenance_whitelist_ok"],
            audit_payload["that_vs_how_passed"],
            audit_payload["anti_legal_persona_passed"],
            audit_payload["first_30s_adsense_safe"],
            audit_payload["spoken_pii_audit_passed"],
            audit_payload["altered_content_disclosure"],
            audited_at,
        ),
    )
    conn.execute(
        "UPDATE episodes SET state = ?, updated_at = ? WHERE episode_id = ?",
        (EPISODE_POST_COMPLIANCE, audited_at, episode_id),
    )

    case_row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    audit_row = conn.execute(
        "SELECT * FROM compliance_audits WHERE audit_id = ?", (resolved_audit_id,)
    ).fetchone()
    cleared = None
    if case_row is not None and audit_row is not None:
        cleared = build_compliance_cleared_case(case_row, audit_row)

    return ComplianceAuditOutcome(
        outcome=COMPLIANCE_PASSED,
        violations=(),
        audit_id=resolved_audit_id,
        compliance_audit=dict(audit_row) if audit_row is not None else audit_payload,
        compliance_cleared_case=cleared,
        episode_state=EPISODE_POST_COMPLIANCE,
    )