"""Offline 90-second slice. No provider socket is opened."""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SCHEMA = REPO / "schema" / "pipeline.sql"
GATES = (
    "FACTUAL_ACCURACY",
    "PRIVACY_PII",
    "SOURCE_RIGHTS",
    "SYNTHETIC_DISCLOSURE",
    "ILLUSTRATIVE_LABELING",
)
SHA = "b" * 64
MOTIFS = (
    "StickmanStage",
    "AudioEvidenceCard",
    "RedactedDocReveal",
    "FoiaFootageFrame",
)


class SliceBlocked(RuntimeError):
    pass


class OfflineTransport:
    """Stand-in for the interactions client. It never opens a socket."""

    def __init__(self) -> None:
        self.calls = 0

    def create(self, prompt: str) -> dict:
        self.calls += 1
        if prompt.startswith("http://") or prompt.startswith("https://"):
            raise SliceBlocked("a provider URL is not a prompt")
        return {"output_tokens": 0, "purpose": "OFFLINE_TEST", "spend_usd": 0.0}


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone() is None:
        connection.executescript(SCHEMA.read_text(encoding="utf8"))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS episode_lock_lease (
          episode_id TEXT PRIMARY KEY,
          holder TEXT NOT NULL,
          acquired_at INTEGER NOT NULL
        )
        """
    )
    return connection


def screen_narration(text: str) -> None:
    folded = text.lower()
    if "living minor" in folded or "juvenile victim" in folded:
        raise SliceBlocked("living-minor narration is refused before a plan is stored")


def screen_source(url: str) -> None:
    folded = url.lower()
    if "youtube.com" in folded or "youtu.be" in folded:
        raise SliceBlocked("competitor video is not a source")


def seed(connection: sqlite3.Connection, narration: str = "At 10:14 PM a silhouette crossed the porch.") -> None:
    screen_narration(narration)
    connection.execute(
        """
        INSERT INTO cases (
          case_id, defendant_name, incident_year, jurisdiction, docket_id,
          primary_record_verified, verification_source, disposition_status,
          conviction_confirmed, anonymization_status, anonymized_by, anonymized_at,
          anonymization_artifact_sha256, created_at, updated_at
        ) VALUES (
          'case_slice','Anon Defendant',2023,'Mercer, NJ','DK-SLICE',
          1,'courtlistener','AFFIRMED',1,'APPROVED','reviewer_a',1000,?,1000,1000
        )
        """,
        (SHA,),
    )
    connection.execute(
        """
        INSERT INTO episodes (
          episode_id, case_id, state, flow_backend_mode, cold_open_archetype,
          total_master_ms, timeline_validated_sha256, ready_bundle_sha256, updated_at, created_at
        ) VALUES (
          'ep_slice','case_slice','MASTERED','GEMINI_OMNI_INTERACTIONS','911_CALL_IN_MEDIA_RES',
          90000,?,?,2000,1000
        )
        """,
        (SHA, SHA),
    )
    connection.execute(
        """
        INSERT INTO scene_plans (
          scene_plan_id, episode_id, scene_id, plan_version, seq_index, story_purpose,
          intended_audience_effect, approved_narration_text, narration_version_sha256,
          cited_fact_ids_json, visual_concept, visual_engine, motif_component, prompt_mode,
          visual_prompt, keyframe_refs_json, expected_output_summary, timing_start_ms,
          timing_end_ms, transition_spec_json, sound_cues_json, edit_instructions,
          acceptance_criteria_json, asset_version_sha256, plan_status, reviewed_by,
          reviewed_at, created_at, updated_at
        ) VALUES (
          'sp_slice','ep_slice','sc_slice',1,1,'Open the file','Orient the viewer',
          ?,?,'["fact_1"]','A quiet desk','CODE_STICKMAN','StickmanStage','TEXT_TO_VIDEO',
          'A quiet desk, no people.','[]','Desk plate',0,90000,
          '{"transition_type":"CUT","duration_ms":0}','[]','Hold the wide shot.',
          '[{"criterion_id":"c1","kind":"SEMANTIC","text":"The desk reads clearly."}]',
          ?,'EDITED_APPROVED','editor_jane',1500,1000,1500
        )
        """,
        (narration, SHA, SHA),
    )
    connection.execute(
        """
        INSERT INTO scenes (
          scene_id, episode_id, scene_plan_id, seq_index, act_number, visual_engine,
          motif_component, start_ms, end_ms, timeline_spec_json
        ) VALUES ('sc_slice','ep_slice','sp_slice',1,1,'CODE_STICKMAN','StickmanStage',0,90000,'{}')
        """
    )
    connection.execute(
        """
        INSERT INTO voice_segments (
          segment_id, episode_id, seq_index, segment_kind, start_ms, end_ms, audio_path
        ) VALUES ('seg_slice','ep_slice',1,'NARRATION',0,90000,'voice/seg_slice.wav')
        """
    )
    connection.execute(
        """
        INSERT INTO provider_spend_reservations (
          reservation_id, episode_id, job_id, attempt_number, provider_id, purpose,
          year_month, estimated_micro_usd, status, created_at
        ) VALUES ('r_slice','ep_slice','job_slice',1,'gemini_omni','OFFLINE_TEST','2026-11',0,'RELEASED',1000)
        """
    )


def approve(connection: sqlite3.Connection) -> None:
    for gate in GATES:
        connection.execute(
            """
            INSERT INTO release_approvals (
              approval_id, episode_id, gate_name, artifact_bundle_sha256, status, reviewer_id, reviewed_at
            ) VALUES (?,?,?,?, 'APPROVED','reviewer_a',2000)
            """,
            (f"ap_{gate}", "ep_slice", gate, SHA),
        )
    connection.execute(
        """
        INSERT INTO qa_reports (
          qa_id, episode_id, integrated_lufs, true_peak_dbtp, lufs_passed, safe_zone_passed,
          vision_frame_qa_status, thumbnail_brand_passed, final_mp4_path, final_mp4_sha256, created_at
        ) VALUES ('qa_slice','ep_slice',-14.0,-1.5,1,1,'PASSED',1,'final.mp4',?,4000)
        """,
        (SHA,),
    )
    connection.execute(
        """
        INSERT INTO compliance_audits (
          audit_id, case_id, provenance_whitelist_ok, that_vs_how_passed, anti_legal_persona_passed,
          first_30s_adsense_safe, spoken_pii_audit_passed, altered_content_disclosure, audited_at
        ) VALUES ('aud_slice','case_slice',1,1,1,1,1,1,4000)
        """
    )


def promote(connection: sqlite3.Connection) -> None:
    connection.execute(
        "UPDATE episodes SET state = 'READY_TO_UPLOAD', updated_at = 3000 WHERE episode_id = 'ep_slice'"
    )


def render_master(out_path: str) -> dict:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    from integration_bridge.episode_picture import DRAW_FPS, HEIGHT, WIDTH, iter_frames

    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}",
        "-framerate", str(DRAW_FPS), "-i", "pipe:0",
        "-f", "lavfi", "-i", "sine=frequency=110:sample_rate=48000:duration=90",
        "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=90,volume=0.35",
        "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "0:v", "-map", "[a]",
        "-vf", "fps=30",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-frames:v", "2700",
        "-shortest",
        str(path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame in iter_frames():
            process.stdin.write(frame)
        process.stdin.close()
        error = process.stderr.read() if process.stderr is not None else b""
        process.wait()
    except Exception:
        process.kill()
        raise
    if process.returncode != 0:
        raise RuntimeError(error.decode("utf-8", "replace")[-800:])
    frames = _probe(path, "nb_frames", "v:0")
    return {"path": str(path), "nb_frames": int(frames), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "integrated_lufs": _lufs(path)}


def run_slice(db_path: str, master_path: str) -> dict:
    transport = OfflineTransport()
    receipt = transport.create("A quiet desk, no people.")
    connection = connect(db_path)
    seed(connection)
    connection.commit()
    try:
        promote(connection)
        connection.commit()
        released = True
    except sqlite3.IntegrityError:
        connection.rollback()
        released = False
    approve(connection)
    promote(connection)
    connection.commit()
    master = render_master(master_path)
    return {
        "released_without_gates": released,
        "motifs": MOTIFS,
        "transport": receipt,
        "master": master,
        "state": connection.execute("SELECT state FROM episodes WHERE episode_id='ep_slice'").fetchone()["state"],
    }


def _probe(path: Path, field: str, stream: str) -> str:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", f"stream={field}", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _lufs(path: Path) -> float:
    result = subprocess.run(["ffmpeg", "-i", str(path), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True, check=False)
    found = None
    for line in result.stderr.splitlines():
        if "I:" in line and "LUFS" in line:
            found = float(line.split("I:", 1)[1].split("LUFS", 1)[0].strip())
    if found is None:
        raise RuntimeError("no loudness")
    return found
