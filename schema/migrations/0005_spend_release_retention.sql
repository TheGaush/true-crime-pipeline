-- Forward migration pipeline.db v4 -> v5.
-- Apply only when meta.schema_version is '4'. Do not run on a database already at 5.
-- Preserves existing rows. Does not DROP tables.
-- Backfill: episodes already READY_TO_UPLOAD or PUBLISHED move to
-- PENDING_HUMAN_SIGNOFF so they must pass the v5 release gate before they ship.

UPDATE meta SET value = '5' WHERE key = 'schema_version' AND value = '4';

INSERT INTO meta (key, value)
SELECT 'live_sandbox_lifetime_cap_micro_usd', '2000000'
WHERE NOT EXISTS (
  SELECT 1 FROM meta WHERE key = 'live_sandbox_lifetime_cap_micro_usd'
);

ALTER TABLE channels_watchlist ADD COLUMN yt_api_purged_at INTEGER;

UPDATE episodes
SET state = 'PENDING_HUMAN_SIGNOFF'
WHERE state IN ('READY_TO_UPLOAD', 'PUBLISHED');

CREATE TABLE credit_refunds (
  refund_id      TEXT PRIMARY KEY,
  account_id     TEXT NOT NULL REFERENCES google_accounts(account_id),
  reservation_id TEXT,
  credits        INTEGER NOT NULL CHECK (credits > 0),
  created_at     INTEGER NOT NULL
) STRICT;

CREATE TRIGGER trg_quota_no_silent_restore
BEFORE UPDATE OF used_today ON quota_buckets
WHEN NEW.used_today < OLD.used_today
  AND NEW.window_reset_at = OLD.window_reset_at
BEGIN
  SELECT RAISE(ABORT, 'QUOTA_SILENT_RESTORE: used_today can decrease only when window_reset_at changes');
END;

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

-- v4 already has this name as an UPDATE-only gate. Replace it; do not drop tables.
DROP TRIGGER IF EXISTS trg_episode_release_gate;

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

CREATE TRIGGER trg_credit_refund_apply
AFTER INSERT ON credit_refunds
BEGIN
  UPDATE google_accounts
  SET daily_credits_left = MIN(daily_credits_cap, daily_credits_left + NEW.credits)
  WHERE account_id = NEW.account_id
    AND NEW.created_at < next_daily_reset_utc_ms;
END;
