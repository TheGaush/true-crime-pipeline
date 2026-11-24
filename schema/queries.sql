-- Canonical SQL Statements for pipeline.db (v5)

-- name: due_watchlist_channels
SELECT channel_id, uploads_playlist_id, median_20_views, yt_ttl_expires_at
FROM channels_watchlist
WHERE is_active = 1
  AND subscriber_count BETWEEN 2000 AND 120000
  AND last_polled_at < :cutoff_ms
ORDER BY last_polled_at ASC
LIMIT :limit;

-- name: purge_expired_yt_api_records
-- Clears YouTube API fields on the candidate. trg_yt_purge_related then clears
-- saturation_checks and the linked channels_watchlist API fields.
UPDATE outlier_candidates
SET raw_yt_payload_json = NULL,
    views_count = NULL,
    outlier_ratio = NULL,
    source_video_id = NULL,
    source_channel_id = NULL,
    saturation_index = 0,
    n_mega_excl = 0,
    n_recent_excl = 0,
    n_14d_excl = 0,
    has_90d_200k_kill = 0,
    composite_score = 0,
    seed_packet_json = '{}',
    yt_data_purged_at = :now_ms,
    status = CASE WHEN status = 'CONSUMED' THEN 'CONSUMED' ELSE 'EXPIRED_TOS_PURGED' END
WHERE track = 'TRACK_A_OUTLIER'
  AND yt_ttl_expires_at <= :now_ms
  AND yt_data_purged_at IS NULL;

-- name: purge_expired_yt_channels
-- Channels with no remaining candidate still lose API fields when their own TTL expires.
UPDATE channels_watchlist
SET channel_name = '',
    subscriber_count = 0,
    median_20_views = 0,
    uploads_playlist_id = '',
    is_active = 0,
    yt_api_purged_at = :now_ms
WHERE yt_ttl_expires_at <= :now_ms
  AND yt_api_purged_at IS NULL;

-- name: consume_quota_bucket
-- :units must be positive. This statement does not reset the window.
-- Call reset_quota_window explicitly when the Pacific day (or other window) rolls.
UPDATE quota_buckets
SET used_today = used_today + :units
WHERE bucket_name = :bucket_name
  AND :units > 0
  AND used_today + :units <= daily_limit
RETURNING bucket_name, used_today, daily_limit;

-- name: reset_quota_window
-- Explicit reset. window_reset_at must move or trg_quota_no_silent_restore aborts.
UPDATE quota_buckets
SET used_today = 0,
    window_reset_at = :now_ms
WHERE bucket_name = :bucket_name
  AND :now_ms != window_reset_at
RETURNING bucket_name, used_today, window_reset_at;

-- name: recent_entropy_window
SELECT episode_id, cold_open_archetype, thumbnail_mood_vec, published_at
FROM published_entropy_history
ORDER BY published_at DESC
LIMIT 5;

-- name: reserve_provider_budget
-- F-01 & F-02: Transactional multi-provider reservation protected by trg_offline_test_zero_spend_guard & trg_provider_global_budget_cap_guard
INSERT INTO provider_spend_reservations (
  reservation_id, episode_id, job_id, attempt_number, provider_id,
  purpose, year_month, estimated_micro_usd, status, created_at
) VALUES (
  :reservation_id, :episode_id, :job_id, :attempt_number, :provider_id,
  :purpose, :year_month, :estimated_micro_usd, 'RESERVED', :now_ms
)
RETURNING reservation_id, estimated_micro_usd, status;

-- name: settle_provider_budget
UPDATE provider_spend_reservations
SET actual_micro_usd = :actual_micro_usd,
    status = :final_status,
    settled_at = :now_ms
WHERE reservation_id = :reservation_id
  AND status IN ('RESERVED', 'UNKNOWN_HOLD')
RETURNING reservation_id, actual_micro_usd, status;

-- name: atomic_refill_and_reserve_daily_account_credits
UPDATE google_accounts
SET
  daily_credits_left = CASE
    WHEN next_daily_reset_utc_ms = 0 OR :now_ms >= next_daily_reset_utc_ms
      THEN daily_credits_cap - :credits
    ELSE daily_credits_left - :credits
  END,
  first_daily_spend_utc_ms = CASE
    WHEN next_daily_reset_utc_ms = 0 OR :now_ms >= next_daily_reset_utc_ms
      THEN :now_ms
    ELSE first_daily_spend_utc_ms
  END,
  next_daily_reset_utc_ms = CASE
    WHEN next_daily_reset_utc_ms = 0 OR :now_ms >= next_daily_reset_utc_ms
      THEN :now_ms + 86400000 + 300000
    ELSE next_daily_reset_utc_ms
  END
WHERE account_id = :account_id
  AND :credits > 0
  AND :credits <= daily_credits_cap
  AND (
    (next_daily_reset_utc_ms = 0 OR :now_ms >= next_daily_reset_utc_ms)
    OR (:now_ms < next_daily_reset_utc_ms AND daily_credits_left >= :credits)
  )
RETURNING account_id, daily_credits_left, first_daily_spend_utc_ms, next_daily_reset_utc_ms;

-- name: refund_daily_account_credits
-- refund_id is the idempotency key. A second insert of the same id fails.
INSERT INTO credit_refunds (refund_id, account_id, reservation_id, credits, created_at)
VALUES (:refund_id, :account_id, :reservation_id, :credits, :now_ms)
RETURNING refund_id, account_id, credits;

-- name: reconcile_unknown_flow_jobs
SELECT
  flow_job_id,
  episode_id,
  scene_id,
  idempotency_key,
  provider_route,
  engine_model,
  provider_operation_id,
  state,
  attempts_used,
  updated_at
FROM flow_jobs
WHERE state IN ('SUBMITTING', 'RUNNING', 'UNKNOWN_RECONCILE')
ORDER BY updated_at ASC;

-- name: batch_desk_queue_oldest_first
SELECT
  fj.flow_job_id,
  fj.episode_id,
  fj.scene_id,
  fj.assigned_account_id,
  fj.engine_model,
  fj.prompt_mode,
  fj.resolution,
  fj.duration_bucket_sec,
  fj.variations,
  fj.estimated_credits,
  fj.start_frame_png,
  fj.end_frame_png,
  fj.prompt_v1,
  fj.prompt_v2_safe,
  fj.attempts_used,
  fj.state,
  e.created_at AS episode_created_at
FROM flow_jobs fj
JOIN episodes e ON e.episode_id = fj.episode_id
WHERE e.state = 'AWAITING_FLOW_BATCH'
  AND fj.provider_route = 'HUMAN_BATCH_DESK'
  AND fj.state IN ('PENDING', 'STRIKE_1_RETRY_SAFE')
ORDER BY e.created_at ASC, fj.assigned_account_id ASC, fj.flow_job_id ASC;

-- name: analytics_performance_by_archetype
SELECT
  e.cold_open_archetype,
  COUNT(DISTINCT e.episode_id) AS episodes,
  AVG(a.ctr_pct) AS avg_ctr,
  AVG(a.retention_30s_pct) AS avg_30s,
  AVG(a.retention_min6_14_pct) AS avg_min6_14,
  AVG(a.avd_pct) AS avg_avd
FROM episodes e
JOIN episode_analytics a ON a.episode_id = e.episode_id
GROUP BY e.cold_open_archetype;
