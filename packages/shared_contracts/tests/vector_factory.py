"""Build the shared 60 valid + 60 adversarial contract vectors."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from shared_contracts.grid import grid_cell_to_pixel_and_zoom
from shared_contracts.models import TOP_LEVEL_MODELS, RELEASE_GATES
from shared_contracts.schema_export import export_contract_schemas

PARITY_MODELS = (
    "SeedPacket",
    "TemporalFactLedger",
    "ComplianceClearedCase",
    "ScenePlan",
    "VoiceTrackManifest",
    "SpatialAnchor",
    "CaseBible",
    "ProductionManifest",
    "TimelineSpec",
    "FlowJobCard",
    "EpisodeAnalyticsSnapshot",
    "ReadyToUploadPack",
)


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _clone(payload: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(payload)


def _entry(model: str, index: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {"model": model, "index": index, "payload": payload}


def seed_valid() -> list[dict[str, Any]]:
    rows = []
    for index in range(5):
        payload: dict[str, Any] = {
            "track": "TRACK_A_OUTLIER" if index % 2 == 0 else "TRACK_B_FOIA_RADAR",
            "suspect_names": [f"Alex Rivera {index}"] if index != 3 else [],
            "victim_names": [] if index != 3 else ["Jordan Hale"],
            "incident_date_or_year": str(1998 + index),
            "county_state": f"King County, WA {index}" if index else "King County, WA",
            "docket_ids": [f"docket_{index}"] if index == 4 else [],
            "unanswered_comment_questions": ["Who signed the affidavit?"] if index == 1 else [],
        }
        if index != 0:
            payload["contract_version"] = "v4"
            payload["lead_classification"] = "LEAD_ONLY"
        if index == 4:
            payload["suspect_names"] = []
            payload["victim_names"] = []
        rows.append(_entry("SeedPacket", index, payload))
    return rows


def fact_valid() -> list[dict[str, Any]]:
    rows = []
    sources = ("court_ruling", "police_affidavit", "news_report", "court_ruling", "police_affidavit")
    for index, source in enumerate(sources):
        fact: dict[str, Any] = {
            "fact_id": f"fact_{index}",
            "case_id": "case_1",
            "datetime_iso": "2014-06-02T15:04:00Z" if index != 2 else "2014-06-02T15:04:00+00:00",
            "event_summary": f"Affidavit notes event {index}",
            "location_text": "entryway",
            "source_type": source,
            "source_doc_id": f"doc_{index}",
            "citation_locator": f"p.{index + 1}",
            "hedging_required": source == "news_report",
        }
        if index == 1:
            fact["physical_clues_json"] = ["overturned table"]
        rows.append(
            _entry(
                "TemporalFactLedger",
                index,
                {"contract_version": "v4", "case_id": "case_1", "facts": [fact]},
            )
        )
    return rows


def compliance_valid() -> list[dict[str, Any]]:
    rows = []
    for index in range(5):
        rows.append(
            _entry(
                "ComplianceClearedCase",
                index,
                {
                    "contract_version": "v4",
                    "case_id": f"case_{index}",
                    "defendant_name": f"Defendant {index}",
                    "incident_year": 2000 + index,
                    "jurisdiction": "Washington",
                    "verification_source": "CourtListener",
                    "disposition_status": "AFFIRMED" if index % 2 == 0 else "STANDING_CONVICTION",
                    "conviction_confirmed": True,
                    "primary_record_verified": True,
                    "anonymization_status": "APPROVED",
                    "anonymized_by": "editor_1",
                    "anonymized_at": 1_700_000_000 + index,
                    "anonymization_artifact_sha256": sha(f"anon-{index}"),
                    "audit_id": f"audit_{index}",
                    "provenance_whitelist_ok": True,
                    "that_vs_how_passed": True,
                    "anti_legal_persona_passed": True,
                    "first_30s_adsense_safe": True,
                    "spoken_pii_audit_passed": True,
                    "altered_content_disclosure": index % 2 == 0,
                    "audited_at": 1_700_000_100 + index,
                },
            )
        )
    return rows


def _criterion(index: int) -> dict[str, Any]:
    return {
        "criterion_id": f"crit_{index}",
        "kind": "SEMANTIC",
        "text": "Does visual match approved narration and cited evidence without misleading the viewer?",
    }


def _transition() -> dict[str, Any]:
    return {"transition_type": "CUT", "duration_ms": 0}


def scene_valid() -> list[dict[str, Any]]:
    specs = [
        ("CODE_STICKMAN", "StickmanStage", "NONE", 0, 8000, "DRAFT"),
        ("AUDIO_EVIDENCE_CARD", "AudioEvidenceCard", "NONE", 0, 6000, "PLAN_APPROVED"),
        ("FOIA_REAL_FOOTAGE", "FoiaFootageFrame", "NONE", 0, 9000, "EDITED_APPROVED"),
        ("FLOW_HERO_VIDEO", "HeroVideoBridge", "TEXT_TO_VIDEO", 0, 8000, "DRAFT"),
        ("STILL_2K_PANZOOM", "Illustrative2KPanZoom", "NONE", 0, 20000, "DRAFT"),
    ]
    rows = []
    for index, (engine, motif, mode, start, end, status) in enumerate(specs):
        payload: dict[str, Any] = {
            "scene_plan_id": f"plan_{index}",
            "episode_id": "ep_1",
            "scene_id": f"scene_{index}",
            "seq_index": index + 1,
            "story_purpose": f"Show the record for beat {index}",
            "intended_audience_effect": "Orient the viewer to the cited record",
            "approved_narration_text": f"According to the affidavit, beat {index} occurred.",
            "narration_version_sha256": sha(f"narr-{index}"),
            "cited_fact_ids_json": [f"fact_{index}"],
            "visual_concept": "Charcoal documentary plate",
            "visual_engine": engine,
            "motif_component": motif,
            "prompt_mode": mode,
            "visual_prompt": "Monochrome charcoal, no graphic injury",
            "expected_output_summary": "A cited visual that matches the narration",
            "timing_start_ms": start,
            "timing_end_ms": end,
            "transition_spec_json": _transition(),
            "edit_instructions": "Hold the cited clue in the safe zone",
            "acceptance_criteria_json": [_criterion(index)],
            "created_at": 100,
            "updated_at": 100 + index,
            "plan_status": status,
        }
        if status in {"PLAN_APPROVED", "EDITED_APPROVED"}:
            payload["reviewed_by"] = "editor_1"
            payload["reviewed_at"] = 200
        if status == "EDITED_APPROVED":
            payload["asset_version_sha256"] = sha(f"asset-{index}")
        if index != 0:
            payload["contract_version"] = "v4"
        rows.append(_entry("ScenePlan", index, payload))
    return rows


def _segment(kind: str, index: int, seq: int, start: int, end: int, episode: str = "ep_1") -> dict[str, Any]:
    segment: dict[str, Any] = {
        "segment_id": f"seg_{index}_{seq}",
        "episode_id": episode,
        "seq_index": seq,
        "segment_kind": kind,
        "start_ms": start,
        "end_ms": end,
    }
    if kind == "NARRATION":
        segment["audio_path"] = f"audio/narr_{index}_{seq}.wav"
        segment["narration_version_sha256"] = sha(f"voice-{index}-{seq}")
    elif kind == "FOIA_AUDIO_SLOT":
        segment["foia_asset_id"] = f"foia_{index}"
    return segment


def voice_valid() -> list[dict[str, Any]]:
    rows = []
    twists = (500, 450, 750, 600, 520)
    for index, twist in enumerate(twists):
        narr_end = 4000 + index * 100
        twist_end = narr_end + twist
        foia_end = twist_end + 2000
        payload: dict[str, Any] = {
            "episode_id": "ep_1",
            "total_master_ms": foia_end,
            "segments": [
                _segment("NARRATION", index, 1, 0, narr_end),
                _segment("TWIST_PAD", index, 2, narr_end, twist_end),
                _segment("FOIA_AUDIO_SLOT", index, 3, twist_end, foia_end),
            ],
        }
        if index == 0:
            payload["word_timestamps"] = [
                {"segment_id": "seg_0_1", "word": "According", "start_ms": 0, "end_ms": 400}
            ]
            payload["cue_points"] = [{"cue_id": "cue_0", "at_ms": 10, "label": "bed"}]
            payload["amplitude_envelope"] = [0.0, 0.5, 1.0]
        else:
            payload["contract_version"] = "v4"
        rows.append(_entry("VoiceTrackManifest", index, payload))
    return rows


def spatial_valid() -> list[dict[str, Any]]:
    rows = []
    base: dict[str, Any] = {
        "anchor_id": "anchor_0",
        "episode_id": "ep_1",
        "still_2k_id": "still_0",
        "clue_name": "overturned table",
        "grid_cell": "A1",
        "x_px": 128,
        "y_px": 72,
    }
    rows.append(_entry("SpatialAnchor", 0, base))
    second = _clone(base)
    second.update({"anchor_id": "anchor_1", "lock_status": "IN_REVIEW", "contract_version": "v4", "cited_fact_id": "fact_1"})
    rows.append(_entry("SpatialAnchor", 1, second))
    third = _clone(base)
    third.update(
        {
            "anchor_id": "anchor_2",
            "lock_status": "LOCKED",
            "locked_by": "editor_1",
            "locked_at": 300,
            "still_asset_sha256": sha("still-2"),
            "contract_version": "v4",
        }
    )
    rows.append(_entry("SpatialAnchor", 2, third))
    fourth = _clone(base)
    fourth.update(
        {
            "anchor_id": "anchor_3",
            "grid_cell": "J10",
            "span_cols": 2.0,
            "span_rows": 1.5,
            "x_px": 2432,
            "y_px": 1368,
            "target_zoom": 1.7,
            "travel_axis": "L_TO_R",
            "contract_version": "v4",
        }
    )
    rows.append(_entry("SpatialAnchor", 3, fourth))
    fifth = _clone(base)
    fifth.update({"anchor_id": "anchor_4", "grid_cell": "A10", "target_zoom": 1.0, "travel_axis": "STATIC", "contract_version": "v4"})
    rows.append(_entry("SpatialAnchor", 4, fifth))
    return rows


def bible_valid() -> list[dict[str, Any]]:
    palette = ["#1B1B1D", "#E9E2D2", "#3A4F66", "#C4A574"]
    rows = []
    for index in range(5):
        style: dict[str, Any] = {"flow_keyframe_safe_palette": palette}
        if index != 0:
            style.update(
                {
                    "evidence_crimson_hex": "#C92A2A",
                    "paper_bg_hex": "#E9E2D2",
                    "ink_hex": "#1B1B1D",
                    "slate_hex": "#3A4F66",
                }
            )
        payload: dict[str, Any] = {
            "episode_id": f"ep_{index}",
            "style_dna_json": style,
            "characters_json": [
                {"character_id": "detective_01", "prop": "notepad", "color_hex": "#3A4F66"},
                {"character_id": "suspect_01", "prop": "coat", "color_hex": "#C4A574"},
            ],
            "locked_at": 500 + index,
        }
        if index:
            payload["contract_version"] = "v4"
        rows.append(_entry("CaseBible", index, payload))
    return rows


def production_valid() -> list[dict[str, Any]]:
    rows = []
    canonical = {
        "manifest_id": "manifest_0",
        "episode_id": "ep_0",
        "case_id": "case_0",
        "cold_open_archetype": "911_CALL_IN_MEDIA_RES",
        "flow_backend_mode": "GEMINI_OMNI_INTERACTIONS",
        "target_duration_ms": 1_200_000,
        "code_foia_ms": 780_000,
        "still_2k_ms": 340_000,
        "hero_ms": 80_000,
        "hero_clip_count": 10,
        "hero_duration_sec": 80,
        "scene_plan_ids": ["plan_0"],
        "voice_total_master_ms": 1_200_000,
    }
    rows.append(_entry("ProductionManifest", 0, canonical))
    archetypes = (
        "SINGLE_FORENSIC_ANOMALY",
        "ALIBI_THAT_CRACKED",
        "CHRONOLOGICAL_COUNTDOWN",
        "911_CALL_IN_MEDIA_RES",
    )
    backends = (
        "VERTEX_VEO_ENTERPRISE",
        "HUMAN_BATCH_DESK",
        "GEMINI_OMNI_INTERACTIONS",
        "VERTEX_VEO_ENTERPRISE",
    )
    for offset, (archetype, backend) in enumerate(zip(archetypes, backends), start=1):
        target = 20_000 + offset * 1000
        hero_sec = 4
        hero_ms = 4000
        still = 5000
        code = target - hero_ms - still
        voice = target - 200
        payload = {
            "contract_version": "v4",
            "manifest_id": f"manifest_{offset}",
            "episode_id": f"ep_{offset}",
            "case_id": f"case_{offset}",
            "fps": 30,
            "cold_open_archetype": archetype,
            "flow_backend_mode": backend,
            "target_duration_ms": target,
            "code_foia_ms": code,
            "still_2k_ms": still,
            "hero_ms": hero_ms,
            "max_hero_clips": 4,
            "max_hero_duration_sec": 20,
            "hero_clip_count": 1,
            "hero_duration_sec": hero_sec,
            "scene_plan_ids": [f"plan_{offset}"],
            "voice_total_master_ms": voice,
            "timeline_validated_sha256": sha(f"timeline-{offset}"),
        }
        rows.append(_entry("ProductionManifest", offset, payload))
    return rows


def timeline_valid() -> list[dict[str, Any]]:
    specs = [
        ("StickmanStage", "TEXT_TO_VIDEO", 8000, False, False),
        ("AudioEvidenceCard", "FIRST_FRAME", 8000, True, False),
        ("RedactedDocReveal", "FIRST_AND_LAST_FRAME", 8000, True, True),
        ("FoiaFootageFrame", "TEXT_TO_VIDEO", 3000, False, False),
        ("StickmanStage", "FIRST_AND_LAST_FRAME", 10000, True, True),
    ]
    rows = []
    for index, (motif, mode, duration, start, end) in enumerate(specs):
        payload: dict[str, Any] = {
            "episode_id": "ep_1",
            "scene_id": f"scene_{index}",
            "scene_plan_id": f"plan_{index}",
            "motif_component": motif,
            "prompt_mode": mode,
            "duration_ms": duration,
        }
        if start:
            payload["start_frame_sha256"] = sha(f"start-{index}")
        if end:
            payload["end_frame_sha256"] = sha(f"end-{index}")
        if index:
            payload["contract_version"] = "v4"
            payload["fps"] = 30
            payload["width_px"] = 1920
            payload["height_px"] = 1080
            payload["motif_registry"] = "MOTIF_REGISTRY_V1"
        rows.append(_entry("TimelineSpec", index, payload))
    return rows


def _fallback(index: int) -> dict[str, Any]:
    return {
        "visual_engine": "CODE_STICKMAN",
        "motif_component": "StickmanStage",
        "reason": f"Neighbor-safe local fallback {index}",
    }


def flow_valid() -> list[dict[str, Any]]:
    specs = [
        ("TEXT_TO_VIDEO", 8, False, False, "PENDING", "GEMINI_OMNI_INTERACTIONS", "gemini-omni-1.2-flash"),
        ("FIRST_FRAME", 8, True, False, "RUNNING", "GEMINI_OMNI_INTERACTIONS", "gemini-omni-1.2-flash"),
        ("FIRST_AND_LAST_FRAME", 8, True, True, "ACCEPTED", "GEMINI_OMNI_INTERACTIONS", "gemini-omni-1.2-flash"),
        ("TEXT_TO_VIDEO", 15, False, False, "SUBMITTING", "VERTEX_VEO_ENTERPRISE", "vertex-veo-enterprise"),
        ("FIRST_FRAME", 3, True, False, "STRIKE_1_RETRY_SAFE", "HUMAN_BATCH_DESK", "manual-desk-video"),
    ]
    rows = []
    for index, (mode, seconds, start, end, state, route, engine) in enumerate(specs):
        payload: dict[str, Any] = {
            "flow_job_id": f"job_{index}",
            "episode_id": "ep_1",
            "scene_id": f"scene_{index}",
            "idempotency_key": f"idem_{index}_key",
            "prompt_mode": mode,
            "duration_bucket_sec": seconds,
            "estimated_micro_usd": 0,
            "prompt_v1": "Monochrome tracking shot, no graphic injury",
            "prompt_v2_safe": "Monochrome camera move across an empty room",
            "fallback_spec_json": _fallback(index),
            "updated_at": 1000 + index,
        }
        if start:
            payload["start_frame_png"] = f"frames/start_{index}.png"
        if end:
            payload["end_frame_png"] = f"frames/end_{index}.png"
        if index:
            payload.update(
                {
                    "contract_version": "v4",
                    "provider_route": route,
                    "engine_model": engine,
                    "resolution": "720p",
                    "variations": 1,
                    "estimated_credits": 0,
                    "attempts_used": 1 if index == 4 else 0,
                    "state": state,
                }
            )
        else:
            payload["state"] = state
        if index == 2:
            payload["output_asset_path"] = "renders/job_2.mp4"
            payload["provider_operation_id"] = "op_2"
        rows.append(_entry("FlowJobCard", index, payload))
    return rows


def analytics_valid() -> list[dict[str, Any]]:
    rows = [
        _entry(
            "EpisodeAnalyticsSnapshot",
            0,
            {
                "snapshot_id": "snap_0",
                "episode_id": "ep_0",
                "days_since_publish": 1,
                "captured_at": 2_000,
            },
        )
    ]
    detailed = [
        ("GREEN_FULL_ADS", "STUDIO_CSV_EXPORT", "STUDIO_CSV_EXPORT", 4.2),
        ("NOT_LINKED", "UNAVAILABLE", "YT_ANALYTICS_API", None),
        ("YELLOW_LIMITED", "MANUAL_CREATOR_ENTRY", "COMBINED", 1.0),
        ("NONE", "STUDIO_CSV_EXPORT", "STUDIO_CSV_EXPORT", 0.0),
    ]
    for offset, (status, source, metrics, ctr) in enumerate(detailed, start=1):
        payload: dict[str, Any] = {
            "contract_version": "v4",
            "snapshot_id": f"snap_{offset}",
            "episode_id": f"ep_{offset}",
            "days_since_publish": offset + 1,
            "watch_hours_total": float(offset),
            "adsense_status": status,
            "adsense_source": source,
            "metrics_source": metrics,
            "captured_at": 3_000 + offset,
        }
        if ctr is not None:
            payload["ctr_pct"] = ctr
            payload["retention_30s_pct"] = 40.0
            payload["retention_min6_14_pct"] = 22.5
            payload["avd_pct"] = 35.0
            payload["rpm_micro_usd"] = 1000
        if source != "UNAVAILABLE":
            payload["adsense_checked_at"] = 4_000 + offset
        rows.append(_entry("EpisodeAnalyticsSnapshot", offset, payload))
    return rows


def ready_valid() -> list[dict[str, Any]]:
    rows = []
    for index in range(5):
        payload = {
            "contract_version": "v4",
            "episode_id": f"ep_{index}",
            "episode_slug": f"ep_slug_{index}",
            "ready_pack_dir": f"ready_to_upload/ep_slug_{index}",
            "ready_bundle_sha256": sha(f"bundle-{index}"),
            "final_mp4_relpath": "final_1080p30.mp4",
            "final_mp4_sha256": sha(f"mp4-{index}"),
            "integrated_lufs": -14.0 if index % 2 == 0 else -14.2,
            "true_peak_dbtp": -1.2 if index % 2 == 0 else -1.5,
            "lufs_passed": True,
            "safe_zone_passed": True,
            "vision_frame_qa_status": "PASSED",
            "thumbnail_brand_passed": True,
            "thumbnail_relpaths": [f"thumbnails/variant_{index}.png"],
            "chapters_relpath": "chapters.txt",
            "youtube_synthetic_disclosure_required": index % 2 == 0,
            "provenance_bundle_relpath": "provenance_bundle.json",
            "qa_certificate_relpath": "qa_certificate.json",
            "human_review_flags": [],
            "approved_release_gates": list(RELEASE_GATES),
        }
        rows.append(_entry("ReadyToUploadPack", index, payload))
    return rows


def valid_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for builder in (
        seed_valid,
        fact_valid,
        compliance_valid,
        scene_valid,
        voice_valid,
        spatial_valid,
        bible_valid,
        production_valid,
        timeline_valid,
        flow_valid,
        analytics_valid,
        ready_valid,
    ):
        rows.extend(builder())
    if len(rows) != 60:
        raise RuntimeError(f"expected 60 valid rows, found {len(rows)}")
    return rows


def _bad(model: str, index: int, payload: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"model": model, "index": index, "payload": payload, "reason": reason}


def adversarial_rows(valid: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, dict[str, Any]] = {}
    for row in valid:
        by_model.setdefault(row["model"], row["payload"])
    rows: list[dict[str, Any]] = []

    seed = _clone(by_model["SeedPacket"])
    extra = _clone(seed)
    extra["narrative_outline"] = "three act structure"
    rows.append(_bad("SeedPacket", 0, extra, "extra_field"))
    long_name = _clone(seed)
    long_name["county_state"] = "A" * 201
    rows.append(_bad("SeedPacket", 1, long_name, "field_too_long"))
    prose = _clone(seed)
    prose["unanswered_comment_questions"] = ["What happened. Then they left town."]
    rows.append(_bad("SeedPacket", 2, prose, "multi_sentence_question"))
    empty = _clone(seed)
    empty["suspect_names"] = []
    empty["victim_names"] = []
    empty["docket_ids"] = []
    rows.append(_bad("SeedPacket", 3, empty, "missing_lookup_key"))
    retired = _clone(seed)
    retired["suspect_names"] = ["VEO_3_1_LITE"]
    rows.append(_bad("SeedPacket", 4, retired, "deprecated_identifier"))

    fact = _clone(by_model["TemporalFactLedger"])
    news = _clone(fact)
    news["facts"][0]["source_type"] = "news_report"
    news["facts"][0]["hedging_required"] = False
    rows.append(_bad("TemporalFactLedger", 0, news, "news_without_hedging"))
    blog = _clone(fact)
    blog["facts"][0]["source_type"] = "blog"
    rows.append(_bad("TemporalFactLedger", 1, blog, "bad_source_type"))
    mismatch = _clone(fact)
    mismatch["facts"][0]["case_id"] = "case_other"
    rows.append(_bad("TemporalFactLedger", 2, mismatch, "case_mismatch"))
    extra_fact = _clone(fact)
    extra_fact["creator_commentary"] = "sensational"
    rows.append(_bad("TemporalFactLedger", 3, extra_fact, "extra_field"))
    empty_facts = _clone(fact)
    empty_facts["facts"] = []
    rows.append(_bad("TemporalFactLedger", 4, empty_facts, "empty_facts"))

    compliance = _clone(by_model["ComplianceClearedCase"])
    reversed_case = _clone(compliance)
    reversed_case["disposition_status"] = "REVERSED"
    rows.append(_bad("ComplianceClearedCase", 0, reversed_case, "disposition"))
    anon = _clone(compliance)
    anon["anonymization_status"] = "NOT_STARTED"
    rows.append(_bad("ComplianceClearedCase", 1, anon, "anonymization"))
    pii = _clone(compliance)
    pii["spoken_pii_audit_passed"] = False
    rows.append(_bad("ComplianceClearedCase", 2, pii, "audit_flag"))
    missing_hash = _clone(compliance)
    del missing_hash["anonymization_artifact_sha256"]
    rows.append(_bad("ComplianceClearedCase", 3, missing_hash, "missing_hash"))
    extra_compliance = _clone(compliance)
    extra_compliance["legal_advice"] = "file a motion"
    rows.append(_bad("ComplianceClearedCase", 4, extra_compliance, "extra_field"))

    scene = _clone(by_model["ScenePlan"])
    extra_scene = _clone(scene)
    extra_scene["story_outline"] = "cold open"
    rows.append(_bad("ScenePlan", 0, extra_scene, "extra_field"))
    frames_only = _clone(scene)
    frames_only["prompt_mode"] = "FRAMES_MOTION_ONLY"
    rows.append(_bad("ScenePlan", 1, frames_only, "deprecated_prompt_mode"))
    old_motif = _clone(scene)
    old_motif["motif_component"] = "CrimeScenePanZoom"
    rows.append(_bad("ScenePlan", 2, old_motif, "deprecated_motif"))
    no_facts = _clone(scene)
    no_facts["cited_fact_ids_json"] = []
    rows.append(_bad("ScenePlan", 3, no_facts, "empty_citations"))
    approved = _clone(scene)
    approved["plan_status"] = "PLAN_APPROVED"
    approved["reviewed_by"] = None
    approved["reviewed_at"] = None
    rows.append(_bad("ScenePlan", 4, approved, "approval_without_reviewer"))

    voice = _clone(by_model["VoiceTrackManifest"])
    extra_voice = _clone(voice)
    extra_voice["beat_outline"] = "act two"
    rows.append(_bad("VoiceTrackManifest", 0, extra_voice, "extra_field"))
    overlap = _clone(voice)
    overlap["segments"] = [
        _segment("NARRATION", 9, 1, 0, 5000),
        _segment("NARRATION", 9, 2, 4000, 8000),
    ]
    overlap["total_master_ms"] = 8000
    overlap["word_timestamps"] = []
    rows.append(_bad("VoiceTrackManifest", 1, overlap, "overlap"))
    twist = {
        "episode_id": "ep_1",
        "total_master_ms": 200,
        "segments": [_segment("TWIST_PAD", 8, 1, 0, 200)],
    }
    rows.append(_bad("VoiceTrackManifest", 2, twist, "twist_too_short"))
    silent = {
        "episode_id": "ep_1",
        "total_master_ms": 1000,
        "segments": [
            {
                "segment_id": "seg_narr",
                "episode_id": "ep_1",
                "seq_index": 1,
                "segment_kind": "NARRATION",
                "start_ms": 0,
                "end_ms": 1000,
                "narration_version_sha256": sha("missing-audio"),
            }
        ],
    }
    rows.append(_bad("VoiceTrackManifest", 3, silent, "narration_without_audio"))
    foia = {
        "episode_id": "ep_1",
        "total_master_ms": 1000,
        "segments": [
            {
                "segment_id": "seg_foia",
                "episode_id": "ep_1",
                "seq_index": 1,
                "segment_kind": "FOIA_AUDIO_SLOT",
                "start_ms": 0,
                "end_ms": 1000,
            }
        ],
    }
    rows.append(_bad("VoiceTrackManifest", 4, foia, "foia_without_asset"))

    spatial = _clone(by_model["SpatialAnchor"])
    extra_anchor = _clone(spatial)
    extra_anchor["sub_quadrant"] = "NE"
    rows.append(_bad("SpatialAnchor", 0, extra_anchor, "extra_field"))
    bad_cell = _clone(spatial)
    bad_cell["grid_cell"] = "K1"
    rows.append(_bad("SpatialAnchor", 1, bad_cell, "grid_cell"))
    unlocked = _clone(spatial)
    unlocked["lock_status"] = "LOCKED"
    rows.append(_bad("SpatialAnchor", 2, unlocked, "lock_without_proof"))
    zoom = _clone(spatial)
    zoom["target_zoom"] = 3.9
    rows.append(_bad("SpatialAnchor", 3, zoom, "zoom_out_of_range"))
    span = _clone(spatial)
    span["span_cols"] = 0
    rows.append(_bad("SpatialAnchor", 4, span, "span_not_positive"))

    bible = _clone(by_model["CaseBible"])
    crimson = _clone(bible)
    crimson["style_dna_json"]["flow_keyframe_safe_palette"] = ["#C92A2A"]
    rows.append(_bad("CaseBible", 0, crimson, "crimson_in_flow_palette"))
    nobody = _clone(bible)
    nobody["characters_json"] = []
    rows.append(_bad("CaseBible", 1, nobody, "no_characters"))
    extra_bible = _clone(bible)
    extra_bible["script"] = "do not store the script here"
    rows.append(_bad("CaseBible", 2, extra_bible, "extra_field"))
    old_version = _clone(bible)
    old_version["contract_version"] = "v3"
    rows.append(_bad("CaseBible", 3, old_version, "contract_version"))
    bad_hex = _clone(bible)
    bad_hex["characters_json"][0]["color_hex"] = "crimson"
    rows.append(_bad("CaseBible", 4, bad_hex, "bad_hex"))

    manifest = _clone(by_model["ProductionManifest"])
    clips = _clone(manifest)
    clips["hero_clip_count"] = 11
    rows.append(_bad("ProductionManifest", 0, clips, "hero_clip_cap"))
    total = _clone(manifest)
    total["target_duration_ms"] = 10
    rows.append(_bad("ProductionManifest", 1, total, "split_mismatch"))
    fps = _clone(manifest)
    fps["fps"] = 24
    rows.append(_bad("ProductionManifest", 2, fps, "fps"))
    drift = _clone(manifest)
    drift["voice_total_master_ms"] = manifest["target_duration_ms"] + 1000
    rows.append(_bad("ProductionManifest", 3, drift, "voice_drift"))
    retired_plan = _clone(manifest)
    retired_plan["scene_plan_ids"] = ["VEO_3_1_LITE"]
    rows.append(_bad("ProductionManifest", 4, retired_plan, "deprecated_identifier"))

    timeline = _clone(by_model["TimelineSpec"])
    none_mode = _clone(timeline)
    none_mode["prompt_mode"] = "NONE"
    rows.append(_bad("TimelineSpec", 0, none_mode, "prompt_mode_none"))
    retired_mode = _clone(timeline)
    retired_mode["prompt_mode"] = "FRAMES_MOTION_ONLY"
    rows.append(_bad("TimelineSpec", 1, retired_mode, "deprecated_prompt_mode"))
    still = _clone(timeline)
    still["motif_component"] = "Illustrative2KPanZoom"
    rows.append(_bad("TimelineSpec", 2, still, "not_an_mvp_motif"))
    retired_motif = _clone(timeline)
    retired_motif["motif_component"] = "CrimeScenePanZoom"
    rows.append(_bad("TimelineSpec", 3, retired_motif, "deprecated_motif"))
    long_both = _clone(timeline)
    long_both["prompt_mode"] = "FIRST_AND_LAST_FRAME"
    long_both["duration_ms"] = 11000
    long_both["start_frame_sha256"] = sha("late-start")
    long_both["end_frame_sha256"] = sha("late-end")
    rows.append(_bad("TimelineSpec", 4, long_both, "first_and_last_over_10s"))

    flow = _clone(by_model["FlowJobCard"])
    extra_flow = _clone(flow)
    extra_flow["usd_per_second"] = 0.1
    rows.append(_bad("FlowJobCard", 0, extra_flow, "extra_field"))
    lite = _clone(flow)
    lite["engine_model"] = "VEO_3_1_LITE"
    rows.append(_bad("FlowJobCard", 1, lite, "deprecated_model"))
    framed = _clone(flow)
    framed["prompt_mode"] = "TEXT_TO_VIDEO"
    framed["start_frame_png"] = "frames/start.png"
    framed["end_frame_png"] = None
    rows.append(_bad("FlowJobCard", 2, framed, "text_to_video_with_frame"))
    twelve = _clone(flow)
    twelve["prompt_mode"] = "FIRST_AND_LAST_FRAME"
    twelve["duration_bucket_sec"] = 12
    twelve["start_frame_png"] = "frames/start.png"
    twelve["end_frame_png"] = "frames/end.png"
    rows.append(_bad("FlowJobCard", 3, twelve, "first_and_last_over_10s"))
    variations = _clone(flow)
    variations["variations"] = 2
    rows.append(_bad("FlowJobCard", 4, variations, "variations"))

    analytics = _clone(by_model["EpisodeAnalyticsSnapshot"])
    extra_analytics = _clone(analytics)
    extra_analytics["monetizationDetails"] = {"status": "on"}
    rows.append(_bad("EpisodeAnalyticsSnapshot", 0, extra_analytics, "extra_field"))
    monetized = _clone(analytics)
    monetized["adsense_status"] = "MONETIZED"
    rows.append(_bad("EpisodeAnalyticsSnapshot", 1, monetized, "fabricated_adsense"))
    day_zero = _clone(analytics)
    day_zero["days_since_publish"] = 0
    rows.append(_bad("EpisodeAnalyticsSnapshot", 2, day_zero, "day_zero"))
    dishonest = _clone(analytics)
    dishonest["adsense_status"] = "GREEN_FULL_ADS"
    dishonest["adsense_source"] = "UNAVAILABLE"
    rows.append(_bad("EpisodeAnalyticsSnapshot", 3, dishonest, "status_without_source"))
    old = _clone(analytics)
    old["contract_version"] = "v2"
    rows.append(_bad("EpisodeAnalyticsSnapshot", 4, old, "contract_version"))

    ready = _clone(by_model["ReadyToUploadPack"])
    gates = _clone(ready)
    gates["approved_release_gates"] = list(RELEASE_GATES[:-1])
    rows.append(_bad("ReadyToUploadPack", 0, gates, "missing_gate"))
    failed = _clone(ready)
    failed["vision_frame_qa_status"] = "FAILED"
    rows.append(_bad("ReadyToUploadPack", 1, failed, "vision_failed"))
    peak = _clone(ready)
    peak["true_peak_dbtp"] = -0.2
    rows.append(_bad("ReadyToUploadPack", 2, peak, "true_peak"))
    extra_ready = _clone(ready)
    extra_ready["upload_now"] = True
    rows.append(_bad("ReadyToUploadPack", 3, extra_ready, "extra_field"))
    traversal = _clone(ready)
    traversal["thumbnail_relpaths"] = ["../secret.png"]
    rows.append(_bad("ReadyToUploadPack", 4, traversal, "path_traversal"))

    if len(rows) != 60:
        raise RuntimeError(f"expected 60 adversarial rows, found {len(rows)}")
    return rows


GRID_ARGS: tuple[dict[str, Any], ...] = (
    {"grid_cell": "A1", "span_cols": 1, "span_rows": 1, "width_px": 2560, "height_px": 1440},
    {"grid_cell": "J10", "span_cols": 1, "span_rows": 1, "width_px": 2560, "height_px": 1440},
    {"grid_cell": "E5", "span_cols": 1, "span_rows": 1, "width_px": 2560, "height_px": 1440},
    {"grid_cell": "A1", "span_cols": 5, "span_rows": 3, "width_px": 2560, "height_px": 1440},
    {"grid_cell": "A1", "span_cols": 1, "span_rows": 4, "width_px": 2560, "height_px": 1440},
    {"grid_cell": "A1", "span_cols": 1, "span_rows": 1, "width_px": 2048, "height_px": 1152},
    {"grid_cell": "J1", "span_cols": 2, "span_rows": 2, "width_px": 2560, "height_px": 1440},
    {"grid_cell": "A10", "span_cols": 8, "span_rows": 1, "width_px": 2560, "height_px": 1440},
)


def build_document() -> dict[str, Any]:
    valid_out = []
    for number, row in enumerate(valid_rows(), start=1):
        model = TOP_LEVEL_MODELS[row["model"]]
        parsed = model.model_validate(row["payload"])
        canonical = json.loads(parsed.model_dump_json())
        again = json.loads(model.model_validate(canonical).model_dump_json())
        if again != canonical:
            raise RuntimeError(f"roundtrip drift for {row['model']} #{row['index']}")
        valid_out.append(
            {
                "id": f"v{number:03d}",
                "model": row["model"],
                "payload": row["payload"],
                "canonical": canonical,
            }
        )
    adversarial_out = []
    from pydantic import ValidationError

    for number, row in enumerate(adversarial_rows([{"model": item["model"], "payload": item["payload"]} for item in valid_out]), start=1):
        model = TOP_LEVEL_MODELS[row["model"]]
        try:
            model.model_validate(row["payload"])
        except ValidationError:
            pass
        else:
            raise RuntimeError(f"adversarial vector was accepted: {row['model']} {row['reason']}")
        adversarial_out.append(
            {
                "id": f"a{number:03d}",
                "model": row["model"],
                "reason": row["reason"],
                "payload": row["payload"],
            }
        )
    grid = []
    for args in GRID_ARGS:
        grid.append({"args": args, "expect": grid_cell_to_pixel_and_zoom(**args)})
    return {
        "contract_version": "v4",
        "valid": valid_out,
        "adversarial": adversarial_out,
        "grid": grid,
    }


def schema_document() -> dict[str, Any]:
    return export_contract_schemas()
