-- Automated True-Crime Pipeline · pipeline.db · schema version 5
-- Authoritative state, multi-provider USD budget ledger, versioned ScenePlan contract,
-- offline-test zero-spend enforcement, and human release sign-off gates.
-- Sole SQLite WAL Writer: Python Backend (apps/batch_desk_ui uses loopback FastAPI HTTP/WS only).
--
-- Runtime & Storage Requirements (F-22):
--   * Minimum SQLite runtime version: >= 3.51.3 (fixes WAL-reset concurrency bug; verified at startup).
--   * Must reside on local host filesystem (NTFS / ext4 / APFS); reject SMB/NFS/UNC paths at startup.
--   * Connection Pragmas:
--       PRAGMA journal_mode = WAL;
--       PRAGMA synchronous = FULL;
--       PRAGMA foreign_keys = ON;
--       PRAGMA busy_timeout = 5000;

--------------------------------------------------------------------------------
-- 0. Metadata, Audit Log & Authoritative Lookup Vocabularies
--------------------------------------------------------------------------------

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
) STRICT, WITHOUT ROWID;

INSERT INTO meta VALUES
  ('schema_version', '5'),
  ('min_sqlite_version', '3.51.3'),
  ('primary_video_model', 'gemini-omni-1.2-flash'),
  ('primary_video_api', 'gemini-interactions-api'),
  ('primary_word_aligner', 'whisperx-local'),
  ('global_monthly_budget_cap_micro_usd', '135000000'),
  ('offline_test_spend_cap_micro_usd', '0'),
  ('live_sandbox_lifetime_cap_micro_usd', '2000000');

CREATE TABLE audit_log (
  audit_seq    INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_id     TEXT NOT NULL,
  action_type  TEXT NOT NULL,
  entity_type  TEXT NOT NULL,
  entity_id    TEXT NOT NULL,
  detail_json  TEXT NOT NULL DEFAULT '{}',
  created_at   INTEGER NOT NULL
) STRICT;

CREATE TABLE episode_states (
  state       TEXT PRIMARY KEY,
  seq_order   INTEGER NOT NULL UNIQUE,
  is_terminal INTEGER NOT NULL DEFAULT 0 CHECK (is_terminal IN (0,1))
) STRICT, WITHOUT ROWID;

INSERT INTO episode_states VALUES
  ('QUEUED', 1, 0),
  ('SCOUTED', 2, 0),
  ('EVIDENCE_AND_2K_LOCKED', 3, 0),
  ('COMPLIANCE_PASSED', 4, 0),
  ('SCENE_PLAN_APPROVED', 5, 0),
  ('VOICE_READY', 6, 0),
  ('MANIFEST_LINTED', 7, 0),
  ('ANIMATIC_APPROVED', 8, 0),
  ('CODE_RENDERED', 9, 0),
  ('AWAITING_FLOW_BATCH', 10, 0),
  ('POST_FLOW_PROCESSING', 11, 0),
  ('MASTERED', 12, 0),
  ('PENDING_HUMAN_SIGNOFF', 13, 0),
  ('READY_TO_UPLOAD', 14, 0),
  ('PUBLISHED', 15, 1),
  ('QUARANTINED_LEGAL_HOLD', 89, 0),
  ('REJECTED_KILL_SWITCH', 90, 1),
  ('ABORTED_COPYCAT_WAVE', 91, 1);

CREATE TABLE visual_engines (
  engine       TEXT PRIMARY KEY,
  paid_video   INTEGER NOT NULL CHECK (paid_video IN (0,1))
) STRICT, WITHOUT ROWID;

INSERT INTO visual_engines VALUES
  ('CODE_STICKMAN', 0),
  ('STILL_2K_PANZOOM', 0),
  ('AUDIO_EVIDENCE_CARD', 0),
  ('FOIA_REAL_FOOTAGE', 0),
  ('FLOW_HERO_VIDEO', 1);

CREATE TABLE flow_job_states (
  state       TEXT PRIMARY KEY,
  is_terminal INTEGER NOT NULL DEFAULT 0 CHECK (is_terminal IN (0,1))
) STRICT, WITHOUT ROWID;

INSERT INTO flow_job_states VALUES
  ('PENDING', 0),
  ('SUBMITTING', 0),
  ('RUNNING', 0),
  ('UNKNOWN_RECONCILE', 0),
  ('PENDING_MANUAL_SPOT_CHECK', 0),
  ('STRIKE_1_RETRY_SAFE', 0),
  ('ACCEPTED', 1),
  ('FAILED_TERMINAL', 1),
  ('SWITCHED_TO_FALLBACK', 1);

CREATE TABLE cold_open_archetypes (
  archetype TEXT PRIMARY KEY
) STRICT, WITHOUT ROWID;

INSERT INTO cold_open_archetypes VALUES
  ('911_CALL_IN_MEDIA_RES'),
  ('SINGLE_FORENSIC_ANOMALY'),
  ('ALIBI_THAT_CRACKED'),
  ('CHRONOLOGICAL_COUNTDOWN');

-- Authoritative Motif Registry V1 (Single Source of Truth across Part 1, Part 2 & Tasks)
CREATE TABLE motif_registry (
  motif_component TEXT PRIMARY KEY,
  owner_package   TEXT NOT NULL CHECK (owner_package IN ('render_catalog','crime_scene_2k','flow_adapter')),
  is_mvp_4        INTEGER NOT NULL DEFAULT 0 CHECK (is_mvp_4 IN (0,1))
) STRICT, WITHOUT ROWID;

INSERT INTO motif_registry VALUES
  ('StickmanStage',          'render_catalog', 1),
  ('AudioEvidenceCard',      'render_catalog', 1),
  ('RedactedDocReveal',      'render_catalog', 1),
  ('FoiaFootageFrame',       'render_catalog', 1),
  ('TimelineScrubber',       'render_catalog', 0),
  ('AnimatedMapRoute',       'render_catalog', 0),
  ('CellTowerTriangulation', 'render_catalog', 0),
  ('SplitScreenComparison',  'render_catalog', 0),
  ('CaseBoardSpine',         'render_catalog', 0),
  ('QuotePullout',           'render_catalog', 0),
  ('EvidenceGridMatrix',     'render_catalog', 0),
  ('ChapterSlateTransition', 'render_catalog', 0),
  ('Illustrative2KPanZoom',  'crime_scene_2k', 0),
  ('HeroVideoBridge',        'flow_adapter',   0);

--------------------------------------------------------------------------------
-- 1. Agent 1 · YouTube Watchlist (Mandatory 30-Day Retention), Quotas & SI
--------------------------------------------------------------------------------

CREATE TABLE quota_buckets (
  bucket_name      TEXT PRIMARY KEY,
  daily_limit      INTEGER NOT NULL CHECK (daily_limit > 0),
  used_today       INTEGER NOT NULL DEFAULT 0 CHECK (used_today >= 0),
  window_reset_at  INTEGER NOT NULL
) STRICT, WITHOUT ROWID;

INSERT INTO quota_buckets VALUES
  ('yt_search', 100, 0, 0),
  ('yt_general', 10000, 0, 0),
  ('yt_insert', 100, 0, 0),
  ('courtlistener', 125, 0, 0);

-- Negative units would lower used_today. A real reset must move window_reset_at.
CREATE TRIGGER trg_quota_no_silent_restore
BEFORE UPDATE OF used_today ON quota_buckets
WHEN NEW.used_today < OLD.used_today
  AND NEW.window_reset_at = OLD.window_reset_at
BEGIN
  SELECT RAISE(ABORT, 'QUOTA_SILENT_RESTORE: used_today can decrease only when window_reset_at changes');
END;

CREATE TABLE channels_watchlist (
  channel_id          TEXT PRIMARY KEY,
  uploads_playlist_id TEXT NOT NULL,
  channel_name        TEXT NOT NULL,
  subscriber_count    INTEGER NOT NULL CHECK (subscriber_count >= 0),
  median_20_views     INTEGER NOT NULL DEFAULT 0 CHECK (median_20_views >= 0),
  last_polled_at      INTEGER NOT NULL DEFAULT 0,
  yt_ttl_expires_at   INTEGER NOT NULL,
  yt_api_purged_at    INTEGER,
  discovered_via      TEXT NOT NULL DEFAULT 'SEED' CHECK (discovered_via IN ('SEED','SPILLOVER')),
  is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
) STRICT, WITHOUT ROWID;

CREATE TABLE outlier_candidates (
  candidate_id           TEXT PRIMARY KEY,
  track                  TEXT NOT NULL CHECK (track IN ('TRACK_A_OUTLIER','TRACK_B_FOIA_RADAR')),
  source_video_id        TEXT,
  source_channel_id      TEXT REFERENCES channels_watchlist(channel_id),
  views_count            INTEGER,
  outlier_ratio          REAL,
  saturation_index       INTEGER NOT NULL CHECK (saturation_index BETWEEN 0 AND 100),
  n_mega_excl            INTEGER NOT NULL DEFAULT 0,
  n_recent_excl          INTEGER NOT NULL DEFAULT 0,
  n_14d_excl             INTEGER NOT NULL DEFAULT 0,
  has_90d_200k_kill      INTEGER NOT NULL DEFAULT 0 CHECK (has_90d_200k_kill IN (0,1)),
  safe_title_ctr_ok      INTEGER NOT NULL DEFAULT 0 CHECK (safe_title_ctr_ok IN (0,1)),
  upgrade_axes_json      TEXT NOT NULL DEFAULT '[]',
  composite_score        REAL NOT NULL DEFAULT 0.0,
  seed_packet_json       TEXT NOT NULL,
  raw_yt_payload_json    TEXT,
  yt_data_purged_at      INTEGER,
  yt_ttl_expires_at      INTEGER,
  policy_kill_reason     TEXT,
  status                 TEXT NOT NULL CHECK (status IN ('CANDIDATE','GREENLIT','REJECTED','CONSUMED','EXPIRED_TOS_PURGED')),
  created_at             INTEGER NOT NULL,
  CHECK (track != 'TRACK_A_OUTLIER' OR yt_ttl_expires_at IS NOT NULL)
) STRICT;

CREATE TABLE saturation_checks (
  check_id           TEXT PRIMARY KEY,
  candidate_id       TEXT NOT NULL REFERENCES outlier_candidates(candidate_id),
  phase              TEXT NOT NULL CHECK (phase IN ('SCOUTING','PRE_RENDER_DAILY_RECHECK')),
  aliases_json       TEXT NOT NULL,
  n_mega_excl        INTEGER NOT NULL,
  n_recent_excl      INTEGER NOT NULL,
  n_14d_wave         INTEGER NOT NULL,
  si_score           INTEGER NOT NULL,
  sunk_cost_override INTEGER NOT NULL DEFAULT 0 CHECK (sunk_cost_override IN (0,1)),
  aborted            INTEGER NOT NULL DEFAULT 0 CHECK (aborted IN (0,1)),
  checked_at         INTEGER NOT NULL
) STRICT;

-- When a Track A row is purged, wipe the saturation rollup and the linked channel API fields.
CREATE TRIGGER trg_yt_purge_related
AFTER UPDATE OF yt_data_purged_at ON outlier_candidates
WHEN NEW.yt_data_purged_at IS NOT NULL AND OLD.yt_data_purged_at IS NULL
BEGIN
  UPDATE saturation_checks
  SET aliases_json = '[]',
      n_mega_excl = 0,
      n_recent_excl = 0,
      n_14d_wave = 0,
      si_score = 0
  WHERE candidate_id = NEW.candidate_id;

  UPDATE channels_watchlist
  SET channel_name = '',
      subscriber_count = 0,
      median_20_views = 0,
      uploads_playlist_id = '',
      is_active = 0,
      yt_api_purged_at = NEW.yt_data_purged_at
  WHERE channel_id = OLD.source_channel_id
    AND yt_api_purged_at IS NULL;
END;

CREATE TABLE courtlistener_cache (
  cache_key    TEXT PRIMARY KEY,
  docket_id    TEXT,
  payload_json TEXT NOT NULL,
  fetched_at   INTEGER NOT NULL,
  expires_at   INTEGER NOT NULL
) STRICT, WITHOUT ROWID;

--------------------------------------------------------------------------------
-- 2. Agents 2 & 3 · Disposition Gate, Explicit Anonymization & Rights Provenance
--------------------------------------------------------------------------------

CREATE TABLE cases (
  case_id                       TEXT PRIMARY KEY,
  candidate_id                  TEXT REFERENCES outlier_candidates(candidate_id),
  defendant_name                TEXT NOT NULL,
  incident_year                 INTEGER NOT NULL,
  jurisdiction                  TEXT NOT NULL,
  docket_id                     TEXT,
  primary_record_verified       INTEGER NOT NULL DEFAULT 0 CHECK (primary_record_verified IN (0,1)),
  verification_source           TEXT NOT NULL,
  disposition_status            TEXT NOT NULL CHECK (disposition_status IN ('AFFIRMED','STANDING_CONVICTION','REVERSED','VACATED','ACQUITTED','PENDING')),
  conviction_confirmed          INTEGER NOT NULL DEFAULT 0 CHECK (conviction_confirmed IN (0,1)),
  anonymization_status          TEXT NOT NULL DEFAULT 'NOT_STARTED' CHECK (anonymization_status IN ('NOT_STARTED','IN_REVIEW','APPROVED')),
  anonymized_by                 TEXT,
  anonymized_at                 INTEGER,
  anonymization_artifact_sha256 TEXT,
  created_at                    INTEGER NOT NULL,
  updated_at                    INTEGER NOT NULL,
  CHECK (anonymization_status != 'APPROVED' OR (anonymized_by IS NOT NULL AND anonymized_at IS NOT NULL AND anonymization_artifact_sha256 IS NOT NULL))
) STRICT;

CREATE TRIGGER trg_case_disposition_guard_insert
BEFORE INSERT ON cases
WHEN NEW.conviction_confirmed = 1 AND NEW.disposition_status NOT IN ('AFFIRMED','STANDING_CONVICTION')
BEGIN
  SELECT RAISE(ABORT, 'LEGAL_DISPOSITION: Cannot confirm conviction when appellate disposition is not AFFIRMED or STANDING_CONVICTION');
END;

CREATE TRIGGER trg_case_disposition_guard_update
BEFORE UPDATE OF disposition_status, conviction_confirmed ON cases
WHEN NEW.conviction_confirmed = 1 AND NEW.disposition_status NOT IN ('AFFIRMED','STANDING_CONVICTION')
BEGIN
  SELECT RAISE(ABORT, 'LEGAL_DISPOSITION: Cannot keep conviction_confirmed=1 after disposition_status changed outside AFFIRMED/STANDING_CONVICTION');
END;

CREATE TRIGGER trg_case_disposition_quarantine
AFTER UPDATE OF disposition_status ON cases
WHEN NEW.disposition_status IN ('REVERSED','VACATED','ACQUITTED','PENDING')
  AND OLD.disposition_status IN ('AFFIRMED','STANDING_CONVICTION')
BEGIN
  UPDATE episodes
  SET state = 'QUARANTINED_LEGAL_HOLD',
      updated_at = NEW.updated_at
  WHERE case_id = NEW.case_id
    AND state NOT IN ('REJECTED_KILL_SWITCH','ABORTED_COPYCAT_WAVE');

  UPDATE release_approvals
  SET status = 'REVOKED',
      notes = 'Auto-revoked: upstream case disposition changed to ' || NEW.disposition_status
  WHERE episode_id IN (SELECT episode_id FROM episodes WHERE case_id = NEW.case_id)
    AND status = 'APPROVED';
END;

CREATE TABLE primary_documents (
  doc_id           TEXT PRIMARY KEY,
  case_id          TEXT NOT NULL REFERENCES cases(case_id),
  source_domain    TEXT NOT NULL,
  source_url       TEXT NOT NULL,
  doc_type         TEXT NOT NULL CHECK (doc_type IN ('court_ruling','police_affidavit','foia_package','gov_release','news_text_only')),
  raw_text_sha256  TEXT NOT NULL,
  local_text_path  TEXT NOT NULL,
  fetched_at       INTEGER NOT NULL
) STRICT;

CREATE TABLE fact_ledger (
  fact_id             TEXT PRIMARY KEY,
  case_id             TEXT NOT NULL REFERENCES cases(case_id),
  datetime_iso        TEXT NOT NULL,
  event_summary       TEXT NOT NULL,
  physical_clues_json TEXT NOT NULL DEFAULT '[]',
  location_text       TEXT NOT NULL,
  source_type         TEXT NOT NULL CHECK (source_type IN ('court_ruling','police_affidavit','news_report')),
  source_doc_id       TEXT NOT NULL REFERENCES primary_documents(doc_id),
  citation_locator    TEXT NOT NULL,
  hedging_required    INTEGER NOT NULL CHECK (hedging_required IN (0,1)),
  contradicts_json    TEXT NOT NULL DEFAULT '[]'
) STRICT;

CREATE TRIGGER trg_fact_news_hedging_insert
BEFORE INSERT ON fact_ledger
WHEN NEW.source_type = 'news_report' AND NEW.hedging_required = 0
BEGIN
  SELECT RAISE(ABORT, 'RULE_09: news_report fact must have hedging_required = 1');
END;

CREATE TRIGGER trg_fact_news_hedging_update
BEFORE UPDATE ON fact_ledger
WHEN NEW.source_type = 'news_report' AND NEW.hedging_required = 0
BEGIN
  SELECT RAISE(ABORT, 'RULE_09: news_report fact must keep hedging_required = 1');
END;

CREATE TABLE foia_media_assets (
  asset_id                    TEXT PRIMARY KEY,
  case_id                     TEXT NOT NULL REFERENCES cases(case_id),
  source_domain               TEXT NOT NULL,
  source_url                  TEXT NOT NULL,
  creator_entity              TEXT NOT NULL,
  rights_holder               TEXT NOT NULL,
  license_basis               TEXT NOT NULL CHECK (license_basis IN (
                                'US_FED_EMPLOYEE_17USC105',
                                'STATE_PUBLIC_RECORD_PERMITTED',
                                'CC0_PUBLIC_DOMAIN',
                                'EXPLICIT_LICENSE_GRANT',
                                'FAIR_USE_REVIEW_REQUIRED',
                                'RESTRICTED_NO_REUSE'
                              )),
  permitted_uses_json         TEXT NOT NULL DEFAULT '[]',
  contains_third_party_attach INTEGER NOT NULL DEFAULT 0 CHECK (contains_third_party_attach IN (0,1)),
  rights_review_status        TEXT NOT NULL DEFAULT 'NOT_STARTED' CHECK (rights_review_status IN ('NOT_STARTED','IN_REVIEW','APPROVED','REJECTED')),
  rights_reviewed_by          TEXT,
  rights_reviewed_at          INTEGER,
  media_kind                  TEXT NOT NULL CHECK (media_kind IN ('bodycam_mp4','dashcam_mp4','court_mp4','call_911_wav','interrogation_wav','photo_cc0')),
  raw_path                    TEXT NOT NULL,
  scrubbed_path               TEXT,
  normalized_cfr_30fps_48k    INTEGER NOT NULL DEFAULT 0 CHECK (normalized_cfr_30fps_48k IN (0,1)),
  music_detected              INTEGER NOT NULL DEFAULT 0 CHECK (music_detected IN (0,1)),
  demucs_applied              INTEGER NOT NULL DEFAULT 0 CHECK (demucs_applied IN (0,1)),
  asr_hypothesis_disagreement REAL NOT NULL DEFAULT 0.0 CHECK (asr_hypothesis_disagreement >= 0.0),
  human_audio_review_required INTEGER NOT NULL DEFAULT 0 CHECK (human_audio_review_required IN (0,1)),
  watermark_clean             INTEGER NOT NULL DEFAULT 0 CHECK (watermark_clean IN (0,1)),
  visual_pii_blurred          INTEGER NOT NULL DEFAULT 0 CHECK (visual_pii_blurred IN (0,1)),
  spoken_pii_bleeped          INTEGER NOT NULL DEFAULT 0 CHECK (spoken_pii_bleeped IN (0,1)),
  profanity_intervals_json    TEXT NOT NULL DEFAULT '[]',
  sha256                      TEXT,
  CHECK (rights_review_status != 'APPROVED' OR (rights_reviewed_by IS NOT NULL AND rights_reviewed_at IS NOT NULL AND license_basis != 'RESTRICTED_NO_REUSE'))
) STRICT;

CREATE TABLE compliance_audits (
  audit_id                   TEXT PRIMARY KEY,
  case_id                    TEXT NOT NULL REFERENCES cases(case_id),
  provenance_whitelist_ok    INTEGER NOT NULL CHECK (provenance_whitelist_ok IN (0,1)),
  that_vs_how_passed         INTEGER NOT NULL CHECK (that_vs_how_passed IN (0,1)),
  anti_legal_persona_passed  INTEGER NOT NULL CHECK (anti_legal_persona_passed IN (0,1)),
  first_30s_adsense_safe     INTEGER NOT NULL CHECK (first_30s_adsense_safe IN (0,1)),
  spoken_pii_audit_passed    INTEGER NOT NULL CHECK (spoken_pii_audit_passed IN (0,1)),
  altered_content_disclosure INTEGER NOT NULL CHECK (altered_content_disclosure IN (0,1)),
  audited_at                 INTEGER NOT NULL
) STRICT;

--------------------------------------------------------------------------------
-- 3. Conveyor Episodes, Illustrative 2K Stills, Versioned ScenePlan Contract, Voice & Scenes
--------------------------------------------------------------------------------

CREATE TABLE episodes (
  episode_id                 TEXT PRIMARY KEY,
  case_id                    TEXT NOT NULL REFERENCES cases(case_id),
  state                      TEXT NOT NULL REFERENCES episode_states(state),
  flow_backend_mode          TEXT NOT NULL DEFAULT 'GEMINI_OMNI_INTERACTIONS'
                             CHECK (flow_backend_mode IN ('GEMINI_OMNI_INTERACTIONS','VERTEX_VEO_ENTERPRISE','HUMAN_BATCH_DESK')),
  cold_open_archetype        TEXT NOT NULL REFERENCES cold_open_archetypes(archetype),
  turning_point_count        INTEGER NOT NULL DEFAULT 0,
  target_duration_ms         INTEGER NOT NULL DEFAULT 1200000,
  total_master_ms            INTEGER NOT NULL DEFAULT 0,
  video_budget_cap_micro_usd INTEGER NOT NULL DEFAULT 10400000 CHECK (video_budget_cap_micro_usd >= 0),
  max_hero_clips             INTEGER NOT NULL DEFAULT 10 CHECK (max_hero_clips BETWEEN 0 AND 10),
  max_hero_duration_sec      INTEGER NOT NULL DEFAULT 80 CHECK (max_hero_duration_sec BETWEEN 0 AND 80),
  timeline_validated_sha256  TEXT,
  altered_content_disclosure INTEGER NOT NULL DEFAULT 1 CHECK (altered_content_disclosure IN (0,1)),
  thumbnail_mood_vec         TEXT,
  ready_pack_dir             TEXT,
  ready_bundle_sha256        TEXT,
  updated_at                 INTEGER NOT NULL,
  created_at                 INTEGER NOT NULL
) STRICT;

CREATE TABLE case_bibles (
  episode_id        TEXT PRIMARY KEY REFERENCES episodes(episode_id),
  style_dna_json    TEXT NOT NULL,
  characters_json   TEXT NOT NULL,
  locked_at         INTEGER NOT NULL
) STRICT, WITHOUT ROWID;

CREATE TABLE still_assets (
  still_2k_id                    TEXT PRIMARY KEY,
  episode_id                     TEXT NOT NULL REFERENCES episodes(episode_id),
  asset_path                     TEXT NOT NULL,
  asset_sha256                   TEXT NOT NULL,
  width_px                       INTEGER NOT NULL CHECK (width_px >= 1920),
  height_px                      INTEGER NOT NULL CHECK (height_px >= 1080),
  is_illustrative_reconstruction INTEGER NOT NULL DEFAULT 1 CHECK (is_illustrative_reconstruction = 1),
  disclaimer_label_text          TEXT NOT NULL DEFAULT 'ILLUSTRATIVE RECONSTRUCTION — NOT CRIME SCENE PHOTO',
  created_at                     INTEGER NOT NULL
) STRICT;

CREATE TABLE spatial_anchors (
  anchor_id            TEXT PRIMARY KEY,
  episode_id           TEXT NOT NULL REFERENCES episodes(episode_id),
  still_2k_id          TEXT NOT NULL REFERENCES still_assets(still_2k_id),
  clue_name            TEXT NOT NULL,
  cited_fact_id        TEXT REFERENCES fact_ledger(fact_id),
  grid_cell            TEXT NOT NULL CHECK (grid_cell GLOB '[A-J][1-9]' OR grid_cell GLOB '[A-J]10'),
  span_cols            REAL NOT NULL DEFAULT 1.0 CHECK (span_cols > 0.0 AND span_cols <= 10.0),
  span_rows            REAL NOT NULL DEFAULT 1.0 CHECK (span_rows > 0.0 AND span_rows <= 10.0),
  x_px                 INTEGER NOT NULL CHECK (x_px >= 0),
  y_px                 INTEGER NOT NULL CHECK (y_px >= 0),
  target_zoom          REAL NOT NULL DEFAULT 2.5 CHECK (target_zoom BETWEEN 1.0 AND 3.8),
  travel_axis          TEXT CHECK (travel_axis IN ('L_TO_R','R_TO_L','STATIC')),
  lock_status          TEXT NOT NULL DEFAULT 'DRAFT' CHECK (lock_status IN ('DRAFT','IN_REVIEW','LOCKED')),
  locked_by            TEXT,
  locked_at            INTEGER,
  still_asset_sha256   TEXT,
  CHECK (lock_status != 'LOCKED' OR (locked_by IS NOT NULL AND locked_at IS NOT NULL AND still_asset_sha256 IS NOT NULL))
) STRICT;

CREATE TABLE voice_segments (
  segment_id      TEXT PRIMARY KEY,
  episode_id      TEXT NOT NULL REFERENCES episodes(episode_id),
  seq_index       INTEGER NOT NULL CHECK (seq_index >= 1),
  segment_kind    TEXT NOT NULL CHECK (segment_kind IN ('NARRATION','FOIA_AUDIO_SLOT','TWIST_PAD')),
  start_ms        INTEGER NOT NULL CHECK (start_ms >= 0),
  end_ms          INTEGER NOT NULL CHECK (end_ms > start_ms),
  audio_path      TEXT,
  foia_asset_id   TEXT REFERENCES foia_media_assets(asset_id),
  UNIQUE (episode_id, seq_index),
  CHECK (
    (segment_kind = 'NARRATION' AND audio_path IS NOT NULL)
    OR (segment_kind = 'FOIA_AUDIO_SLOT' AND foia_asset_id IS NOT NULL)
    OR (segment_kind = 'TWIST_PAD')
  )
) STRICT;

CREATE TRIGGER trg_voice_segments_no_overlap_insert
BEFORE INSERT ON voice_segments
WHEN EXISTS (
  SELECT 1 FROM voice_segments vs
  WHERE vs.episode_id = NEW.episode_id
    AND NEW.start_ms < vs.end_ms
    AND NEW.end_ms > vs.start_ms
)
BEGIN
  SELECT RAISE(ABORT, 'TIMELINE_OVERLAP: voice_segments intervals must not overlap within an episode');
END;

CREATE TRIGGER trg_voice_segments_no_overlap_update
BEFORE UPDATE OF start_ms, end_ms, episode_id ON voice_segments
WHEN EXISTS (
  SELECT 1 FROM voice_segments vs
  WHERE vs.episode_id = NEW.episode_id
    AND vs.segment_id != NEW.segment_id
    AND NEW.start_ms < vs.end_ms
    AND NEW.end_ms > vs.start_ms
)
BEGIN
  SELECT RAISE(ABORT, 'TIMELINE_OVERLAP: updated voice_segments interval overlaps an existing segment');
END;

-- F-05 & F-06: Versioned ScenePlan Contract enforcing Plan First -> Creation Second -> Editing Last
CREATE TABLE scene_plans (
  scene_plan_id              TEXT PRIMARY KEY,
  episode_id                 TEXT NOT NULL REFERENCES episodes(episode_id),
  scene_id                   TEXT NOT NULL,
  plan_version               INTEGER NOT NULL DEFAULT 1 CHECK (plan_version >= 1),
  seq_index                  INTEGER NOT NULL CHECK (seq_index >= 1),
  story_purpose              TEXT NOT NULL,
  intended_audience_effect   TEXT NOT NULL,
  approved_narration_text    TEXT NOT NULL,
  narration_version_sha256   TEXT NOT NULL,
  cited_fact_ids_json        TEXT NOT NULL CHECK (cited_fact_ids_json != '[]'),
  visual_concept             TEXT NOT NULL,
  visual_engine              TEXT NOT NULL REFERENCES visual_engines(engine),
  motif_component            TEXT NOT NULL REFERENCES motif_registry(motif_component),
  prompt_mode                TEXT NOT NULL CHECK (prompt_mode IN ('NONE','TEXT_TO_VIDEO','FIRST_FRAME','FIRST_AND_LAST_FRAME')),
  visual_prompt              TEXT NOT NULL,
  keyframe_refs_json         TEXT NOT NULL DEFAULT '[]',
  expected_output_summary    TEXT NOT NULL,
  timing_start_ms            INTEGER NOT NULL CHECK (timing_start_ms >= 0),
  timing_end_ms              INTEGER NOT NULL CHECK (timing_end_ms > timing_start_ms),
  transition_spec_json       TEXT NOT NULL,
  sound_cues_json            TEXT NOT NULL DEFAULT '[]',
  edit_instructions          TEXT NOT NULL,
  acceptance_criteria_json   TEXT NOT NULL CHECK (acceptance_criteria_json != '[]'),
  asset_version_sha256       TEXT,
  plan_status                TEXT NOT NULL DEFAULT 'DRAFT'
                             CHECK (plan_status IN ('DRAFT','PLAN_APPROVED','ASSETS_CREATED','EDITED_APPROVED','STALE_NEEDS_REAPPROVAL')),
  reviewed_by                TEXT,
  reviewed_at                INTEGER,
  created_at                 INTEGER NOT NULL,
  updated_at                 INTEGER NOT NULL,
  UNIQUE (episode_id, scene_id, plan_version),
  CHECK (plan_status NOT IN ('PLAN_APPROVED','EDITED_APPROVED') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
  CHECK (plan_status != 'EDITED_APPROVED' OR asset_version_sha256 IS NOT NULL)
) STRICT;

-- F-05: Changing narration invalidates approved plan & upstream assets, preventing stale audio/visual mismatches!
CREATE TRIGGER trg_scene_plan_invalidate_on_narration_edit
BEFORE UPDATE OF approved_narration_text, narration_version_sha256, timing_start_ms, timing_end_ms ON scene_plans
WHEN OLD.narration_version_sha256 != NEW.narration_version_sha256
  AND OLD.plan_status IN ('PLAN_APPROVED','ASSETS_CREATED','EDITED_APPROVED')
BEGIN
  UPDATE scene_plans
  SET plan_status = 'STALE_NEEDS_REAPPROVAL',
      asset_version_sha256 = NULL
  WHERE scene_plan_id = NEW.scene_plan_id;

  UPDATE episodes
  SET timeline_validated_sha256 = NULL,
      updated_at = NEW.updated_at
  WHERE episode_id = NEW.episode_id;
END;

CREATE TABLE scenes (
  scene_id             TEXT PRIMARY KEY,
  episode_id           TEXT NOT NULL REFERENCES episodes(episode_id),
  scene_plan_id        TEXT NOT NULL REFERENCES scene_plans(scene_plan_id),
  seq_index            INTEGER NOT NULL CHECK (seq_index >= 1),
  act_number           INTEGER NOT NULL CHECK (act_number IN (1,2,3)),
  visual_engine        TEXT NOT NULL REFERENCES visual_engines(engine),
  motif_component      TEXT NOT NULL REFERENCES motif_registry(motif_component),
  start_ms             INTEGER NOT NULL CHECK (start_ms >= 0),
  end_ms               INTEGER NOT NULL CHECK (end_ms > start_ms),
  emotional_peak_score REAL NOT NULL DEFAULT 0.0,
  timeline_spec_json   TEXT NOT NULL,
  fallback_spec_json   TEXT,
  rendered_mp4_path    TEXT,
  rendered_sha256      TEXT,
  UNIQUE (episode_id, seq_index)
) STRICT;

CREATE TRIGGER trg_scenes_no_overlap_insert
BEFORE INSERT ON scenes
WHEN EXISTS (
  SELECT 1 FROM scenes s
  WHERE s.episode_id = NEW.episode_id
    AND NEW.start_ms < s.end_ms
    AND NEW.end_ms > s.start_ms
)
BEGIN
  SELECT RAISE(ABORT, 'TIMELINE_OVERLAP: scenes intervals must not overlap within an episode');
END;

CREATE TRIGGER trg_scenes_no_overlap_update
BEFORE UPDATE OF start_ms, end_ms, episode_id ON scenes
WHEN EXISTS (
  SELECT 1 FROM scenes s
  WHERE s.episode_id = NEW.episode_id
    AND s.scene_id != NEW.scene_id
    AND NEW.start_ms < s.end_ms
    AND NEW.end_ms > s.start_ms
)
BEGIN
  SELECT RAISE(ABORT, 'TIMELINE_OVERLAP: updated scene interval overlaps an existing scene');
END;

CREATE TABLE published_entropy_history (
  episode_id            TEXT PRIMARY KEY REFERENCES episodes(episode_id),
  cold_open_archetype   TEXT NOT NULL REFERENCES cold_open_archetypes(archetype),
  turning_point_count   INTEGER NOT NULL CHECK (turning_point_count >= 3),
  thumbnail_mood_vec    TEXT NOT NULL,
  published_at          INTEGER NOT NULL
) STRICT, WITHOUT ROWID;

--------------------------------------------------------------------------------
-- 4. Multi-Provider Global Monthly Budget Ledger, External Video Jobs & Crash Safety (F-01, F-02, F-10)
--------------------------------------------------------------------------------

-- F-02: Global across-all-providers + per-provider monthly budget caps in authoritative pipeline.db
CREATE TABLE monthly_budget_ledger (
  year_month         TEXT NOT NULL,       -- e.g. '2026-11'
  provider_id        TEXT NOT NULL,       -- 'ALL_PROVIDERS' | 'gemini_omni' | 'gemini_image' | 'deepseek_chat' | 'tts' | 'vision_qa'
  hard_cap_micro_usd INTEGER NOT NULL CHECK (hard_cap_micro_usd >= 0),
  PRIMARY KEY (year_month, provider_id)
) STRICT, WITHOUT ROWID;

INSERT INTO monthly_budget_ledger VALUES
  ('2026-11', 'ALL_PROVIDERS', 135000000),  -- $135.00/mo global autonomous ceiling across ALL providers
  ('2026-11', 'gemini_omni',   104000000),  -- $104.00/mo ceiling (10 eps * $10.40)
  ('2026-11', 'gemini_image',    5000000),  --  $5.00/mo
  ('2026-11', 'deepseek_chat',  38000000),  -- $38.00/mo conservative NO-cache upper bound
  ('2026-11', 'tts',             5000000),  --  $5.00/mo
  ('2026-11', 'vision_qa',       2000000);  --  $2.00/mo

CREATE TABLE google_accounts (
  account_id               TEXT PRIMARY KEY,
  label                    TEXT NOT NULL,
  monthly_credits_left     INTEGER NOT NULL DEFAULT 1000 CHECK (monthly_credits_left >= 0),
  daily_credits_cap        INTEGER NOT NULL DEFAULT 50 CHECK (daily_credits_cap > 0),
  daily_credits_left       INTEGER NOT NULL DEFAULT 50 CHECK (daily_credits_left >= 0),
  first_daily_spend_utc_ms INTEGER NOT NULL DEFAULT 0,
  next_daily_reset_utc_ms  INTEGER NOT NULL DEFAULT 0,
  nano_pro_daily_left      INTEGER NOT NULL DEFAULT 100 CHECK (nano_pro_daily_left >= 0),
  upscale_2k_daily_left    INTEGER NOT NULL DEFAULT 200 CHECK (upscale_2k_daily_left >= 0)
) STRICT, WITHOUT ROWID;

INSERT INTO google_accounts VALUES
  ('acct_1', 'Optional Pro #1', 1000, 50, 50, 0, 0, 100, 200),
  ('acct_2', 'Optional Pro #2', 1000, 50, 50, 0, 0, 100, 200),
  ('acct_3', 'Optional Pro #3', 1000, 50, 50, 0, 0, 100, 200);

CREATE TABLE flow_jobs (
  flow_job_id           TEXT PRIMARY KEY,
  episode_id            TEXT NOT NULL REFERENCES episodes(episode_id),
  scene_id              TEXT NOT NULL REFERENCES scenes(scene_id),
  idempotency_key       TEXT NOT NULL UNIQUE,
  assigned_account_id   TEXT REFERENCES google_accounts(account_id),
  provider_route        TEXT NOT NULL DEFAULT 'GEMINI_OMNI_INTERACTIONS'
                        CHECK (provider_route IN ('GEMINI_OMNI_INTERACTIONS','VERTEX_VEO_ENTERPRISE','HUMAN_BATCH_DESK')),
  engine_model          TEXT NOT NULL DEFAULT 'gemini-omni-1.2-flash'
                        CHECK (engine_model IN ('gemini-omni-1.2-flash','vertex-veo-enterprise','manual-desk-video')),
  prompt_mode           TEXT NOT NULL CHECK (prompt_mode IN ('TEXT_TO_VIDEO','FIRST_FRAME','FIRST_AND_LAST_FRAME')),
  resolution            TEXT NOT NULL DEFAULT '720p' CHECK (resolution IN ('360p','720p','1080p','4k')),
  duration_bucket_sec   INTEGER NOT NULL CHECK (duration_bucket_sec BETWEEN 3 AND 15),
  variations            INTEGER NOT NULL DEFAULT 1 CHECK (variations = 1),
  estimated_micro_usd   INTEGER NOT NULL DEFAULT 800000 CHECK (estimated_micro_usd >= 0),
  estimated_credits     INTEGER NOT NULL DEFAULT 0 CHECK (estimated_credits >= 0),
  start_frame_png       TEXT,
  end_frame_png         TEXT,
  prompt_v1             TEXT NOT NULL,
  prompt_v2_safe        TEXT NOT NULL,
  fallback_spec_json    TEXT NOT NULL,
  provider_operation_id TEXT,
  attempts_used         INTEGER NOT NULL DEFAULT 0 CHECK (attempts_used BETWEEN 0 AND 2),
  state                 TEXT NOT NULL DEFAULT 'PENDING' REFERENCES flow_job_states(state),
  output_asset_path     TEXT,
  updated_at            INTEGER NOT NULL,
  UNIQUE (episode_id, scene_id),
  CHECK (
    (prompt_mode = 'TEXT_TO_VIDEO' AND start_frame_png IS NULL AND end_frame_png IS NULL)
    OR (prompt_mode = 'FIRST_FRAME' AND start_frame_png IS NOT NULL AND end_frame_png IS NULL)
    OR (prompt_mode = 'FIRST_AND_LAST_FRAME' AND start_frame_png IS NOT NULL AND end_frame_png IS NOT NULL AND duration_bucket_sec BETWEEN 3 AND 10)
  )
) STRICT;

-- Cumulative hero clip count and duration. Failed jobs no longer occupy the cap.
CREATE TRIGGER trg_flow_hero_cap_insert
BEFORE INSERT ON flow_jobs
WHEN NEW.state != 'FAILED_TERMINAL'
  AND (
    (SELECT COUNT(*) FROM flow_jobs fj
      WHERE fj.episode_id = NEW.episode_id AND fj.state != 'FAILED_TERMINAL') + 1
      > (SELECT max_hero_clips FROM episodes WHERE episode_id = NEW.episode_id)
    OR
    (SELECT COALESCE(SUM(fj.duration_bucket_sec), 0) FROM flow_jobs fj
      WHERE fj.episode_id = NEW.episode_id AND fj.state != 'FAILED_TERMINAL')
      + NEW.duration_bucket_sec
      > (SELECT max_hero_duration_sec FROM episodes WHERE episode_id = NEW.episode_id)
  )
BEGIN
  SELECT RAISE(ABORT, 'HERO_CAP_EXCEEDED: cumulative hero clip count or duration exceeds the episode cap');
END;

CREATE TRIGGER trg_flow_hero_cap_update
BEFORE UPDATE OF duration_bucket_sec, state, episode_id ON flow_jobs
WHEN NEW.state != 'FAILED_TERMINAL'
  AND (
    (SELECT COUNT(*) FROM flow_jobs fj
      WHERE fj.episode_id = NEW.episode_id
        AND fj.flow_job_id != OLD.flow_job_id
        AND fj.state != 'FAILED_TERMINAL') + 1
      > (SELECT max_hero_clips FROM episodes WHERE episode_id = NEW.episode_id)
    OR
    (SELECT COALESCE(SUM(fj.duration_bucket_sec), 0) FROM flow_jobs fj
      WHERE fj.episode_id = NEW.episode_id
        AND fj.flow_job_id != OLD.flow_job_id
        AND fj.state != 'FAILED_TERMINAL')
      + NEW.duration_bucket_sec
      > (SELECT max_hero_duration_sec FROM episodes WHERE episode_id = NEW.episode_id)
  )
BEGIN
  SELECT RAISE(ABORT, 'HERO_CAP_EXCEEDED: cumulative hero clip count or duration exceeds the episode cap');
END;

-- F-01 & F-02: Cross-provider transactional USD spend reservation ledger
CREATE TABLE provider_spend_reservations (
  reservation_id      TEXT PRIMARY KEY,
  episode_id          TEXT REFERENCES episodes(episode_id),
  job_id              TEXT NOT NULL,
  attempt_number      INTEGER NOT NULL CHECK (attempt_number >= 1),
  provider_id         TEXT NOT NULL CHECK (provider_id IN ('gemini_omni','gemini_image','deepseek_chat','tts','vision_qa','vertex_veo')),
  purpose             TEXT NOT NULL CHECK (purpose IN ('PRODUCTION','LIVE_SANDBOX','OFFLINE_TEST')),
  year_month          TEXT NOT NULL,
  estimated_micro_usd INTEGER NOT NULL CHECK (estimated_micro_usd >= 0),
  actual_micro_usd    INTEGER CHECK (actual_micro_usd >= 0),
  status              TEXT NOT NULL CHECK (status IN ('RESERVED','COMMITTED','RELEASED','UNKNOWN_HOLD')),
  created_at          INTEGER NOT NULL,
  settled_at          INTEGER,
  UNIQUE (job_id, attempt_number)
) STRICT;

-- F-01: Routine offline tests MUST maintain strict zero billable spend
CREATE TRIGGER trg_offline_test_zero_spend_guard
BEFORE INSERT ON provider_spend_reservations
WHEN NEW.purpose = 'OFFLINE_TEST' AND NEW.estimated_micro_usd > 0
BEGIN
  SELECT RAISE(ABORT, 'OFFLINE_TEST_ZERO_SPEND: Ordinary tests must use transport mocks with $0 estimated spend');
END;

-- F-02: Enforce per-episode video cap, per-provider monthly cap, AND global ALL_PROVIDERS monthly cap atomically!
CREATE TRIGGER trg_provider_global_budget_cap_guard
BEFORE INSERT ON provider_spend_reservations
WHEN NEW.purpose IN ('PRODUCTION','LIVE_SANDBOX')
  AND (
    -- 1. Must have configured provider & ALL_PROVIDERS cap rows for this month
    NOT EXISTS (SELECT 1 FROM monthly_budget_ledger WHERE year_month = NEW.year_month AND provider_id = 'ALL_PROVIDERS')
    OR NOT EXISTS (SELECT 1 FROM monthly_budget_ledger WHERE year_month = NEW.year_month AND provider_id = NEW.provider_id)
    -- 2. Global across-all-providers monthly cap check
    OR (
      SELECT COALESCE(SUM(
        CASE WHEN status = 'COMMITTED' THEN COALESCE(actual_micro_usd, estimated_micro_usd)
             WHEN status IN ('RESERVED','UNKNOWN_HOLD') THEN estimated_micro_usd ELSE 0 END
      ), 0)
      FROM provider_spend_reservations
      WHERE year_month = NEW.year_month
    ) + NEW.estimated_micro_usd > (
      SELECT hard_cap_micro_usd FROM monthly_budget_ledger WHERE year_month = NEW.year_month AND provider_id = 'ALL_PROVIDERS'
    )
    -- 3. Per-provider monthly cap check
    OR (
      SELECT COALESCE(SUM(
        CASE WHEN status = 'COMMITTED' THEN COALESCE(actual_micro_usd, estimated_micro_usd)
             WHEN status IN ('RESERVED','UNKNOWN_HOLD') THEN estimated_micro_usd ELSE 0 END
      ), 0)
      FROM provider_spend_reservations
      WHERE year_month = NEW.year_month AND provider_id = NEW.provider_id
    ) + NEW.estimated_micro_usd > (
      SELECT hard_cap_micro_usd FROM monthly_budget_ledger WHERE year_month = NEW.year_month AND provider_id = NEW.provider_id
    )
    -- 4. Per-episode video cap check when reserving paid video
    OR (
      NEW.episode_id IS NOT NULL
      AND NEW.provider_id IN ('gemini_omni','vertex_veo')
      AND (
        SELECT COALESCE(SUM(
          CASE WHEN status = 'COMMITTED' THEN COALESCE(actual_micro_usd, estimated_micro_usd)
               WHEN status IN ('RESERVED','UNKNOWN_HOLD') THEN estimated_micro_usd ELSE 0 END
        ), 0)
        FROM provider_spend_reservations
        WHERE episode_id = NEW.episode_id AND provider_id IN ('gemini_omni','vertex_veo')
      ) + NEW.estimated_micro_usd > (
        SELECT video_budget_cap_micro_usd FROM episodes WHERE episode_id = NEW.episode_id
      )
    )
  )
BEGIN
  SELECT RAISE(ABORT, 'GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED: Multi-provider or per-episode USD reservation ceiling reached');
END;

-- Settlement cannot hide a positive charge as RELEASED, cannot bill an offline test,
-- and must re-check caps using the post-update contribution (actual when committed).
CREATE TRIGGER trg_budget_settlement_guard
BEFORE UPDATE OF actual_micro_usd, estimated_micro_usd, status, purpose ON provider_spend_reservations
WHEN
  (COALESCE(NEW.actual_micro_usd, 0) > 0 AND NEW.status = 'RELEASED')
  OR (NEW.status = 'COMMITTED' AND NEW.actual_micro_usd IS NULL)
  OR (
    (NEW.purpose = 'OFFLINE_TEST' OR OLD.purpose = 'OFFLINE_TEST')
    AND (COALESCE(NEW.estimated_micro_usd, 0) > 0 OR COALESCE(NEW.actual_micro_usd, 0) > 0)
  )
  OR (
    NEW.purpose IN ('PRODUCTION', 'LIVE_SANDBOX')
    AND (
      (
        SELECT COALESCE(SUM(
          CASE WHEN status = 'COMMITTED' THEN COALESCE(actual_micro_usd, estimated_micro_usd)
               WHEN status IN ('RESERVED', 'UNKNOWN_HOLD') THEN estimated_micro_usd
               ELSE 0 END
        ), 0)
        FROM provider_spend_reservations
        WHERE year_month = NEW.year_month
          AND reservation_id != OLD.reservation_id
      )
      + CASE
          WHEN NEW.status = 'COMMITTED' THEN COALESCE(NEW.actual_micro_usd, NEW.estimated_micro_usd)
          WHEN NEW.status IN ('RESERVED', 'UNKNOWN_HOLD') THEN NEW.estimated_micro_usd
          ELSE 0
        END
      > (
        SELECT hard_cap_micro_usd FROM monthly_budget_ledger
        WHERE year_month = NEW.year_month AND provider_id = 'ALL_PROVIDERS'
      )
      OR (
        SELECT COALESCE(SUM(
          CASE WHEN status = 'COMMITTED' THEN COALESCE(actual_micro_usd, estimated_micro_usd)
               WHEN status IN ('RESERVED', 'UNKNOWN_HOLD') THEN estimated_micro_usd
               ELSE 0 END
        ), 0)
        FROM provider_spend_reservations
        WHERE year_month = NEW.year_month
          AND provider_id = NEW.provider_id
          AND reservation_id != OLD.reservation_id
      )
      + CASE
          WHEN NEW.status = 'COMMITTED' THEN COALESCE(NEW.actual_micro_usd, NEW.estimated_micro_usd)
          WHEN NEW.status IN ('RESERVED', 'UNKNOWN_HOLD') THEN NEW.estimated_micro_usd
          ELSE 0
        END
      > (
        SELECT hard_cap_micro_usd FROM monthly_budget_ledger
        WHERE year_month = NEW.year_month AND provider_id = NEW.provider_id
      )
    )
  )
BEGIN
  SELECT RAISE(ABORT, 'BUDGET_SETTLEMENT_BLOCKED: settlement would release a positive charge, bill an offline test, or exceed a cap');
END;

-- One authorized sandbox run, including retries, cannot exceed $2 for the life of the database.
CREATE TRIGGER trg_live_sandbox_lifetime_cap_insert
BEFORE INSERT ON provider_spend_reservations
WHEN NEW.purpose = 'LIVE_SANDBOX'
  AND (
    SELECT COALESCE(SUM(
      CASE WHEN status = 'COMMITTED' THEN COALESCE(actual_micro_usd, estimated_micro_usd)
           WHEN status IN ('RESERVED', 'UNKNOWN_HOLD') THEN estimated_micro_usd
           ELSE 0 END
    ), 0)
    FROM provider_spend_reservations
    WHERE purpose = 'LIVE_SANDBOX'
  ) + NEW.estimated_micro_usd
  > CAST((SELECT value FROM meta WHERE key = 'live_sandbox_lifetime_cap_micro_usd') AS INTEGER)
BEGIN
  SELECT RAISE(ABORT, 'LIVE_SANDBOX_CAP_EXCEEDED: authorized sandbox spend including retries is capped at $2');
END;

CREATE TRIGGER trg_live_sandbox_lifetime_cap_update
BEFORE UPDATE OF actual_micro_usd, estimated_micro_usd, status, purpose ON provider_spend_reservations
WHEN NEW.purpose = 'LIVE_SANDBOX'
  AND (
    SELECT COALESCE(SUM(
      CASE WHEN status = 'COMMITTED' THEN COALESCE(actual_micro_usd, estimated_micro_usd)
           WHEN status IN ('RESERVED', 'UNKNOWN_HOLD') THEN estimated_micro_usd
           ELSE 0 END
    ), 0)
    FROM provider_spend_reservations
    WHERE purpose = 'LIVE_SANDBOX'
      AND reservation_id != OLD.reservation_id
  )
  + CASE
      WHEN NEW.status = 'COMMITTED' THEN COALESCE(NEW.actual_micro_usd, NEW.estimated_micro_usd)
      WHEN NEW.status IN ('RESERVED', 'UNKNOWN_HOLD') THEN NEW.estimated_micro_usd
      ELSE 0
    END
  > CAST((SELECT value FROM meta WHERE key = 'live_sandbox_lifetime_cap_micro_usd') AS INTEGER)
BEGIN
  SELECT RAISE(ABORT, 'LIVE_SANDBOX_CAP_EXCEEDED: authorized sandbox spend including retries is capped at $2');
END;

CREATE TABLE flow_job_attempts (
  attempt_id            TEXT PRIMARY KEY,
  flow_job_id           TEXT NOT NULL REFERENCES flow_jobs(flow_job_id),
  attempt_number        INTEGER NOT NULL CHECK (attempt_number IN (1,2)),
  provider_operation_id TEXT,
  prompt_used           TEXT NOT NULL,
  cost_micro_usd        INTEGER NOT NULL DEFAULT 0 CHECK (cost_micro_usd >= 0),
  credits_charged       INTEGER NOT NULL DEFAULT 0 CHECK (credits_charged >= 0),
  pool_source           TEXT NOT NULL CHECK (pool_source IN ('GEMINI_API_USD','VERTEX_USD','DAILY_CREDITS','MONTHLY_CREDITS')),
  qa_verdict            TEXT NOT NULL CHECK (qa_verdict IN ('PASS','PENDING_MANUAL_SPOT_CHECK','FAIL_SAFETY_BLOCK','FAIL_MORPH','FAIL_DURATION_RES','UNKNOWN_TIMEOUT')),
  qa_notes              TEXT,
  created_at            INTEGER NOT NULL,
  UNIQUE (flow_job_id, attempt_number)
) STRICT;

CREATE TRIGGER trg_flow_two_strike_breaker
BEFORE INSERT ON flow_job_attempts
WHEN (SELECT attempts_used FROM flow_jobs WHERE flow_job_id = NEW.flow_job_id) >= 2
BEGIN
  SELECT RAISE(ABORT, 'LAW_3_BREAKER: 2-Strike Circuit Breaker tripped; must switch to fallback_spec');
END;

--------------------------------------------------------------------------------
-- 5. Mandatory 5-Gate Human Release Sign-Off (F-05, F-06) & Honest Analytics (F-12)
--------------------------------------------------------------------------------

CREATE TABLE release_approvals (
  approval_id            TEXT PRIMARY KEY,
  episode_id             TEXT NOT NULL REFERENCES episodes(episode_id),
  gate_name              TEXT NOT NULL CHECK (gate_name IN (
                           'FACTUAL_ACCURACY',
                           'PRIVACY_PII',
                           'SOURCE_RIGHTS',
                           'SYNTHETIC_DISCLOSURE',
                           'ILLUSTRATIVE_LABELING'
                         )),
  artifact_bundle_sha256 TEXT NOT NULL,
  status                 TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','REVOKED')),
  reviewer_id            TEXT,
  reviewed_at            INTEGER,
  notes                  TEXT,
  UNIQUE (episode_id, gate_name, artifact_bundle_sha256),
  CHECK (status NOT IN ('APPROVED','REJECTED') OR (reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL))
) STRICT;

CREATE TABLE qa_reports (
  qa_id                    TEXT PRIMARY KEY,
  episode_id               TEXT NOT NULL REFERENCES episodes(episode_id),
  integrated_lufs          REAL NOT NULL,
  true_peak_dbtp           REAL NOT NULL,
  lufs_passed              INTEGER NOT NULL CHECK (lufs_passed IN (0,1)),
  safe_zone_passed         INTEGER NOT NULL CHECK (safe_zone_passed IN (0,1)),
  vision_frame_qa_status   TEXT NOT NULL CHECK (vision_frame_qa_status IN ('PASSED','FAILED','PENDING_MANUAL_SPOT_CHECK')),
  thumbnail_brand_passed   INTEGER NOT NULL CHECK (thumbnail_brand_passed IN (0,1)),
  final_mp4_path           TEXT NOT NULL,
  final_mp4_sha256         TEXT NOT NULL,
  created_at               INTEGER NOT NULL
) STRICT;

-- Release checks shared by INSERT and UPDATE OF state. Fail closed on QA and open review.
CREATE TRIGGER trg_episode_release_gate_insert
BEFORE INSERT ON episodes
WHEN NEW.state IN ('READY_TO_UPLOAD','PUBLISHED')
  AND (
    NOT EXISTS (
      SELECT 1 FROM cases c
      WHERE c.case_id = NEW.case_id
        AND c.disposition_status IN ('AFFIRMED','STANDING_CONVICTION')
        AND c.anonymization_status = 'APPROVED'
        AND c.primary_record_verified = 1
        AND c.conviction_confirmed = 1
    )
    OR NEW.timeline_validated_sha256 IS NULL
    OR NEW.ready_bundle_sha256 IS NULL
    OR NOT EXISTS (SELECT 1 FROM scenes s WHERE s.episode_id = NEW.episode_id)
    OR EXISTS (
      SELECT 1 FROM scenes s
      JOIN scene_plans sp ON sp.scene_plan_id = s.scene_plan_id
      WHERE s.episode_id = NEW.episode_id
        AND sp.plan_status != 'EDITED_APPROVED'
    )
    OR EXISTS (
      SELECT 1 FROM flow_jobs fj
      WHERE fj.episode_id = NEW.episode_id
        AND fj.state IN ('PENDING','SUBMITTING','RUNNING','UNKNOWN_RECONCILE','PENDING_MANUAL_SPOT_CHECK','STRIKE_1_RETRY_SAFE')
    )
    OR (
      SELECT COUNT(DISTINCT gate_name)
      FROM release_approvals ra
      WHERE ra.episode_id = NEW.episode_id
        AND ra.artifact_bundle_sha256 = NEW.ready_bundle_sha256
        AND ra.status = 'APPROVED'
    ) < 5
    OR NOT EXISTS (
      SELECT 1 FROM qa_reports q
      WHERE q.episode_id = NEW.episode_id
        AND q.vision_frame_qa_status = 'PASSED'
        AND q.lufs_passed = 1
        AND q.safe_zone_passed = 1
        AND q.thumbnail_brand_passed = 1
        AND q.integrated_lufs BETWEEN -14.5 AND -13.5
    )
    OR EXISTS (
      SELECT 1 FROM foia_media_assets a
      WHERE a.case_id = NEW.case_id
        AND a.human_audio_review_required = 1
    )
    OR NOT EXISTS (
      SELECT 1 FROM compliance_audits ca
      WHERE ca.case_id = NEW.case_id
        AND ca.provenance_whitelist_ok = 1
        AND ca.that_vs_how_passed = 1
        AND ca.anti_legal_persona_passed = 1
        AND ca.first_30s_adsense_safe = 1
        AND ca.spoken_pii_audit_passed = 1
        AND ca.altered_content_disclosure = 1
    )
  )
BEGIN
  SELECT RAISE(ABORT, 'RELEASE_GATE_BLOCKED: insert of a releasable episode failed primary-record, conviction, QA, compliance, or 5-gate checks');
END;

CREATE TRIGGER trg_episode_release_gate
BEFORE UPDATE OF state ON episodes
WHEN NEW.state IN ('READY_TO_UPLOAD','PUBLISHED')
  AND (
    NOT EXISTS (
      SELECT 1 FROM cases c
      WHERE c.case_id = NEW.case_id
        AND c.disposition_status IN ('AFFIRMED','STANDING_CONVICTION')
        AND c.anonymization_status = 'APPROVED'
        AND c.primary_record_verified = 1
        AND c.conviction_confirmed = 1
    )
    OR NEW.timeline_validated_sha256 IS NULL
    OR NEW.ready_bundle_sha256 IS NULL
    OR NOT EXISTS (SELECT 1 FROM scenes s WHERE s.episode_id = NEW.episode_id)
    OR EXISTS (
      SELECT 1 FROM scenes s
      JOIN scene_plans sp ON sp.scene_plan_id = s.scene_plan_id
      WHERE s.episode_id = NEW.episode_id
        AND sp.plan_status != 'EDITED_APPROVED'
    )
    OR EXISTS (
      SELECT 1 FROM flow_jobs fj
      WHERE fj.episode_id = NEW.episode_id
        AND fj.state IN ('PENDING','SUBMITTING','RUNNING','UNKNOWN_RECONCILE','PENDING_MANUAL_SPOT_CHECK','STRIKE_1_RETRY_SAFE')
    )
    OR (
      SELECT COUNT(DISTINCT gate_name)
      FROM release_approvals ra
      WHERE ra.episode_id = NEW.episode_id
        AND ra.artifact_bundle_sha256 = NEW.ready_bundle_sha256
        AND ra.status = 'APPROVED'
    ) < 5
    OR NOT EXISTS (
      SELECT 1 FROM qa_reports q
      WHERE q.episode_id = NEW.episode_id
        AND q.vision_frame_qa_status = 'PASSED'
        AND q.lufs_passed = 1
        AND q.safe_zone_passed = 1
        AND q.thumbnail_brand_passed = 1
        AND q.integrated_lufs BETWEEN -14.5 AND -13.5
    )
    OR EXISTS (
      SELECT 1 FROM foia_media_assets a
      WHERE a.case_id = NEW.case_id
        AND a.human_audio_review_required = 1
    )
    OR NOT EXISTS (
      SELECT 1 FROM compliance_audits ca
      WHERE ca.case_id = NEW.case_id
        AND ca.provenance_whitelist_ok = 1
        AND ca.that_vs_how_passed = 1
        AND ca.anti_legal_persona_passed = 1
        AND ca.first_30s_adsense_safe = 1
        AND ca.spoken_pii_audit_passed = 1
        AND ca.altered_content_disclosure = 1
    )
  )
BEGIN
  SELECT RAISE(ABORT, 'RELEASE_GATE_BLOCKED: Requires verified primary record, confirmed conviction, APPROVED anonymization, EDITED_APPROVED plans, passed QA, compliance audit, settled jobs, and all 5 human release approvals');
END;

-- A released episode leaves READY/PUBLISHED when the bundle hash or timeline hash changes.
CREATE TRIGGER trg_episode_release_invalidate_bundle
AFTER UPDATE OF ready_bundle_sha256, timeline_validated_sha256 ON episodes
WHEN OLD.state IN ('READY_TO_UPLOAD','PUBLISHED')
  AND NEW.state IN ('READY_TO_UPLOAD','PUBLISHED')
  AND (
    IFNULL(NEW.ready_bundle_sha256, '') != IFNULL(OLD.ready_bundle_sha256, '')
    OR IFNULL(NEW.timeline_validated_sha256, '') != IFNULL(OLD.timeline_validated_sha256, '')
  )
BEGIN
  UPDATE episodes
  SET state = 'PENDING_HUMAN_SIGNOFF'
  WHERE episode_id = NEW.episode_id
    AND state IN ('READY_TO_UPLOAD','PUBLISHED');
END;

CREATE TRIGGER trg_release_invalidate_on_plan
AFTER UPDATE OF plan_status ON scene_plans
WHEN NEW.plan_status != 'EDITED_APPROVED'
BEGIN
  UPDATE episodes
  SET state = 'PENDING_HUMAN_SIGNOFF',
      timeline_validated_sha256 = NULL
  WHERE episode_id = NEW.episode_id
    AND state IN ('READY_TO_UPLOAD','PUBLISHED');
END;

CREATE TRIGGER trg_release_invalidate_on_qa
AFTER UPDATE OF vision_frame_qa_status, lufs_passed, safe_zone_passed, thumbnail_brand_passed, integrated_lufs ON qa_reports
WHEN NEW.vision_frame_qa_status != 'PASSED'
  OR NEW.lufs_passed != 1
  OR NEW.safe_zone_passed != 1
  OR NEW.thumbnail_brand_passed != 1
  OR NEW.integrated_lufs < -14.5
  OR NEW.integrated_lufs > -13.5
BEGIN
  UPDATE episodes
  SET state = 'PENDING_HUMAN_SIGNOFF'
  WHERE episode_id = NEW.episode_id
    AND state IN ('READY_TO_UPLOAD','PUBLISHED');
END;

CREATE TRIGGER trg_release_invalidate_on_approval
AFTER UPDATE OF status, artifact_bundle_sha256 ON release_approvals
WHEN NEW.status != 'APPROVED'
BEGIN
  UPDATE episodes
  SET state = 'PENDING_HUMAN_SIGNOFF'
  WHERE episode_id = NEW.episode_id
    AND state IN ('READY_TO_UPLOAD','PUBLISHED');
END;

CREATE TABLE episode_analytics (
  snapshot_id            TEXT PRIMARY KEY,
  episode_id             TEXT NOT NULL REFERENCES episodes(episode_id),
  days_since_publish     INTEGER NOT NULL CHECK (days_since_publish >= 1),
  ctr_pct                REAL,
  retention_30s_pct      REAL,
  retention_min6_14_pct  REAL,
  avd_pct                REAL,
  watch_hours_total      REAL NOT NULL DEFAULT 0.0,
  rpm_micro_usd          INTEGER,
  adsense_status         TEXT NOT NULL DEFAULT 'UNKNOWN'
                         CHECK (adsense_status IN ('UNKNOWN','PENDING','NOT_LINKED','GREEN_FULL_ADS','YELLOW_LIMITED','NONE')),
  adsense_source         TEXT NOT NULL DEFAULT 'UNAVAILABLE'
                         CHECK (adsense_source IN ('STUDIO_CSV_EXPORT','MANUAL_CREATOR_ENTRY','UNAVAILABLE')),
  adsense_checked_at     INTEGER,
  metrics_source         TEXT NOT NULL DEFAULT 'YT_ANALYTICS_API'
                         CHECK (metrics_source IN ('YT_ANALYTICS_API','STUDIO_CSV_EXPORT','COMBINED')),
  captured_at            INTEGER NOT NULL
) STRICT;

--------------------------------------------------------------------------------
-- 6. Views for Conveyor & Global Budget Monitoring
--------------------------------------------------------------------------------

CREATE VIEW v_active_conveyor AS
SELECT
  e.episode_id,
  e.state,
  e.flow_backend_mode,
  e.video_budget_cap_micro_usd,
  COALESCE((
    SELECT SUM(CASE WHEN r.status = 'COMMITTED' THEN COALESCE(r.actual_micro_usd, r.estimated_micro_usd)
                    WHEN r.status IN ('RESERVED','UNKNOWN_HOLD') THEN r.estimated_micro_usd ELSE 0 END)
    FROM provider_spend_reservations r
    WHERE r.episode_id = e.episode_id AND r.provider_id IN ('gemini_omni','vertex_veo')
  ), 0) AS video_reserved_or_spent_micro_usd,
  COUNT(fj.flow_job_id) AS total_flow_jobs,
  SUM(CASE WHEN fj.state IN ('ACCEPTED','SWITCHED_TO_FALLBACK') THEN 1 ELSE 0 END) AS completed_flow_jobs
FROM episodes e
LEFT JOIN flow_jobs fj ON fj.episode_id = e.episode_id
WHERE e.state NOT IN ('PUBLISHED','REJECTED_KILL_SWITCH','ABORTED_COPYCAT_WAVE')
GROUP BY e.episode_id
ORDER BY e.created_at ASC;

-- Idempotent daily-credit refunds. The primary key is the refund id, not the amount.
CREATE TABLE credit_refunds (
  refund_id      TEXT PRIMARY KEY,
  account_id     TEXT NOT NULL REFERENCES google_accounts(account_id),
  reservation_id TEXT,
  credits        INTEGER NOT NULL CHECK (credits > 0),
  created_at     INTEGER NOT NULL
) STRICT;

CREATE TRIGGER trg_credit_refund_apply
AFTER INSERT ON credit_refunds
BEGIN
  UPDATE google_accounts
  SET daily_credits_left = MIN(daily_credits_cap, daily_credits_left + NEW.credits)
  WHERE account_id = NEW.account_id
    AND NEW.created_at < next_daily_reset_utc_ms;
END;
