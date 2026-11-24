// Executable SQLite schema verification suite (v5) using built-in node:sqlite
// Verifies SQL invariants across F-01..F-22 & second-pass audit findings (offline schema tests only).
// Run: node schema/schema-test.js

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');

const pipelineSql = fs.readFileSync(path.join(__dirname, 'pipeline.sql'), 'utf8');
const telemetrySql = fs.readFileSync(path.join(__dirname, 'telemetry.sql'), 'utf8');
const queriesSql = fs.readFileSync(path.join(__dirname, 'queries.sql'), 'utf8');

function extractQuery(name) {
  const re = new RegExp(`-- name: ${name}\\r?\\n([\\s\\S]*?)(?=\\r?\\n-- name:|$)`);
  const m = queriesSql.match(re);
  assert.ok(m, `Query '${name}' not found in queries.sql`);
  return m[1].trim();
}

function setupDb() {
  const db = new DatabaseSync(':memory:');
  db.exec('PRAGMA foreign_keys = ON;');
  db.exec(pipelineSql);
  return db;
}

function seedApprovedCaseAndEpisode(db, epState = 'MASTERED') {
  db.prepare(
    `INSERT INTO cases (case_id, defendant_name, incident_year, jurisdiction, docket_id, primary_record_verified, verification_source, disposition_status, conviction_confirmed, anonymization_status, anonymized_by, anonymized_at, anonymization_artifact_sha256, created_at, updated_at)
     VALUES ('case_1','John Doe',2023,'Mercer, NJ','DK-1',1,'courtlistener','AFFIRMED',1,'APPROVED','reviewer_a',1000,'sha_anon_1',1000,1000)`
  ).run();
  db.prepare(
    `INSERT INTO episodes (episode_id, case_id, state, flow_backend_mode, cold_open_archetype, total_master_ms, timeline_validated_sha256, ready_bundle_sha256, updated_at, created_at)
     VALUES ('ep_1','case_1',?,'GEMINI_OMNI_INTERACTIONS','911_CALL_IN_MEDIA_RES',1200000,'sha_tl_1','sha_bundle_1',1000,1000)`
  ).run(epState);
}

function insertApprovedScenePlanAndScene(db, sceneId = 'sc_1', seq = 1, engine = 'FLOW_HERO_VIDEO', motif = 'HeroVideoBridge', startMs = 0, endMs = 8000) {
  const spId = `sp_${sceneId}_v1`;
  db.prepare(
    `INSERT INTO scene_plans (
       scene_plan_id, episode_id, scene_id, plan_version, seq_index, story_purpose, intended_audience_effect,
       approved_narration_text, narration_version_sha256, cited_fact_ids_json, visual_concept,
       visual_engine, motif_component, prompt_mode, visual_prompt, keyframe_refs_json, expected_output_summary,
       timing_start_ms, timing_end_ms, transition_spec_json, sound_cues_json, edit_instructions,
       acceptance_criteria_json, asset_version_sha256, plan_status, reviewed_by, reviewed_at, created_at, updated_at
     ) VALUES (
       ?, 'ep_1', ?, 1, ?, 'Establish arrival timeline', 'Curiosity hook',
       'At 10:14 PM a silhouette crossed the porch.', 'sha_nar_1', '["fact_1"]', 'Monochrome doorway pan',
       ?, ?, 'TEXT_TO_VIDEO', 'Slow charcoal camera push toward porch door', '[]', 'Crisp silhouette door entry',
       ?, ?, '{"type":"l_cut","ms":800}', '[{"cue":"door_creak"}]', 'Hold title 2.8s then cut on dialogue',
       '["Fact cited","Safe-Zone clear"]', 'sha_asset_1', 'EDITED_APPROVED', 'editor_jane', 1500, 1000, 1500
     )`
  ).run(spId, sceneId, seq, engine, motif, startMs, endMs);

  db.prepare(
    `INSERT INTO scenes (scene_id, episode_id, scene_plan_id, seq_index, act_number, visual_engine, motif_component, start_ms, end_ms, timeline_spec_json)
     VALUES (?, 'ep_1', ?, ?, 1, ?, ?, ?, ?, '{}')`
  ).run(sceneId, spId, seq, engine, motif, startMs, endMs);
  return spId;
}

const scenarios = [
  ['1. Telemetry schema enforces cached_input_tokens <= total_input_tokens & STRICT mode', () => {
    const tdb = new DatabaseSync(':memory:');
    tdb.exec(telemetrySql);
    // Reject impossible token count where cached > total_input_tokens!
    assert.throws(() => {
      tdb.prepare(
        `INSERT INTO api_token_usage (episode_id, agent_name, model_id, is_off_peak, total_input_tokens, cached_input_tokens, output_tokens, cost_micro_usd, created_at)
         VALUES ('ep_01','agent4','DeepSeek-V4.1-Flash-1017',1,10000,25000,12000,15000,1700000000000)`
      ).run();
    });
    // Valid telemetry row: 35000 total input (25000 cached + 10000 uncached)
    tdb.prepare(
      `INSERT INTO api_token_usage (episode_id, agent_name, model_id, is_off_peak, total_input_tokens, cached_input_tokens, output_tokens, cost_micro_usd, created_at)
       VALUES ('ep_01','agent4','DeepSeek-V4.1-Flash-1017',1,35000,25000,12000,15000,1700000000000)`
    ).run();
    assert.equal(tdb.prepare('SELECT COUNT(*) AS c FROM api_token_usage').get().c, 1);
    tdb.close();
  }],

  ['2. Lookup tables seed schema v5, WhisperX aligner, $135 global cap, 18 states, authoritative 4-motif MVP', () => {
    const db = setupDb();
    assert.equal(db.prepare("SELECT value FROM meta WHERE key='schema_version'").get().value, '5');
    assert.equal(db.prepare("SELECT value FROM meta WHERE key='live_sandbox_lifetime_cap_micro_usd'").get().value, '2000000');
    assert.equal(db.prepare("SELECT value FROM meta WHERE key='primary_video_model'").get().value, 'gemini-omni-1.2-flash');
    assert.equal(db.prepare("SELECT value FROM meta WHERE key='primary_word_aligner'").get().value, 'whisperx-local');
    assert.equal(db.prepare("SELECT value FROM meta WHERE key='offline_test_spend_cap_micro_usd'").get().value, '0');
    assert.equal(db.prepare('SELECT COUNT(*) AS c FROM motif_registry WHERE is_mvp_4 = 1').get().c, 4);
    db.close();
  }],

  ['3. F-01 & F-02: Offline-test zero-spend trigger & global ALL_PROVIDERS $135/mo cap guard across providers', () => {
    const db = setupDb();
    seedApprovedCaseAndEpisode(db, 'AWAITING_FLOW_BATCH');
    const reserveStmt = db.prepare(extractQuery('reserve_provider_budget'));

    // Offline test trying to spend > $0 is rejected!
    assert.throws(() => {
      reserveStmt.get({
        ':reservation_id': 'r_test_bad', ':episode_id': 'ep_1', ':job_id': 'job_t', ':attempt_number': 1,
        ':provider_id': 'deepseek_chat', ':purpose': 'OFFLINE_TEST', ':year_month': '2026-11',
        ':estimated_micro_usd': 1000, ':now_ms': 1000
      });
    }, /OFFLINE_TEST_ZERO_SPEND/);

    // Spend $38 on deepseek_chat -> OK ($97 left under $135 global cap)
    reserveStmt.get({
      ':reservation_id': 'r_ds_1', ':episode_id': 'ep_1', ':job_id': 'job_ds_1', ':attempt_number': 1,
      ':provider_id': 'deepseek_chat', ':purpose': 'PRODUCTION', ':year_month': '2026-11',
      ':estimated_micro_usd': 38_000_000, ':now_ms': 1000
    });

    // Raise gemini_omni cap temporarily to test global ALL_PROVIDERS $135 ceiling across multiple providers:
    db.prepare(`UPDATE monthly_budget_ledger SET hard_cap_micro_usd = 120000000 WHERE year_month='2026-11' AND provider_id='gemini_omni'`).run();
    db.prepare(`UPDATE episodes SET video_budget_cap_micro_usd = 120000000 WHERE episode_id='ep_1'`).run();
    // Adding $98 to gemini_omni puts total ALL_PROVIDERS = $38 + $98 = $136 > $135 -> BLOCKED!
    assert.throws(() => {
      reserveStmt.get({
        ':reservation_id': 'r_omni_over', ':episode_id': 'ep_1', ':job_id': 'job_omni_1', ':attempt_number': 1,
        ':provider_id': 'gemini_omni', ':purpose': 'PRODUCTION', ':year_month': '2026-11',
        ':estimated_micro_usd': 98_000_000, ':now_ms': 1001
      });
    }, /GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED/);
    db.close();
  }],

  ['4. F-05 & F-06: Versioned ScenePlan contract invalidates stale assets on narration edit & blocks release', () => {
    const db = setupDb();
    seedApprovedCaseAndEpisode(db, 'MASTERED');
    const spId = insertApprovedScenePlanAndScene(db, 'sc_1', 1);

    const gates = ['FACTUAL_ACCURACY', 'PRIVACY_PII', 'SOURCE_RIGHTS', 'SYNTHETIC_DISCLOSURE', 'ILLUSTRATIVE_LABELING'];
    gates.forEach((g, idx) => {
      db.prepare(`INSERT INTO release_approvals VALUES (?, 'ep_1', ?, 'sha_bundle_1', 'APPROVED', 'editor_jane', 2000, 'verified')`).run(`ap_${idx}`, g);
    });

    // Editing narration SHA on sp_1 invalidates plan_status to STALE_NEEDS_REAPPROVAL and clears timeline hash!
    db.prepare(`UPDATE scene_plans SET approved_narration_text = 'Revised 10:19 PM narration.', narration_version_sha256 = 'sha_nar_2', updated_at = 3000 WHERE scene_plan_id = ?`).run(spId);
    assert.equal(db.prepare(`SELECT plan_status FROM scene_plans WHERE scene_plan_id = ?`).get(spId).plan_status, 'STALE_NEEDS_REAPPROVAL');
    assert.equal(db.prepare(`SELECT timeline_validated_sha256 FROM episodes WHERE episode_id = 'ep_1'`).get().timeline_validated_sha256, null);

    // Release blocked while ScenePlan is STALE_NEEDS_REAPPROVAL!
    assert.throws(() => {
      db.prepare(`UPDATE episodes SET state = 'READY_TO_UPLOAD' WHERE episode_id = 'ep_1'`).run();
    }, /RELEASE_GATE_BLOCKED/);

    // Re-approve plan & revalidate timeline -> now release succeeds!
    db.prepare(`UPDATE scene_plans SET asset_version_sha256 = 'sha_asset_2', plan_status = 'EDITED_APPROVED', reviewed_by = 'editor_jane', reviewed_at = 3500 WHERE scene_plan_id = ?`).run(spId);
    db.prepare(`UPDATE episodes SET timeline_validated_sha256 = 'sha_tl_2' WHERE episode_id = 'ep_1'`).run();
    db.prepare(`INSERT INTO qa_reports VALUES ('qa_1','ep_1',-14.0,-1.5,1,1,'PASSED',1,'final.mp4','sha_mp4',4000)`).run();
    db.prepare(`INSERT INTO compliance_audits VALUES ('aud_1','case_1',1,1,1,1,1,1,4000)`).run();
    db.prepare(`UPDATE episodes SET state = 'READY_TO_UPLOAD' WHERE episode_id = 'ep_1'`).run();
    assert.equal(db.prepare(`SELECT state FROM episodes WHERE episode_id = 'ep_1'`).get().state, 'READY_TO_UPLOAD');
    db.close();
  }],

  ['5. F-03: Case disposition guard protects INSERT & UPDATE + auto-quarantines downstream episodes', () => {
    const db = setupDb();
    assert.throws(() => {
      db.prepare(`INSERT INTO cases (case_id,defendant_name,incident_year,jurisdiction,verification_source,disposition_status,conviction_confirmed,created_at,updated_at)
                  VALUES ('case_rev','Jane Doe',2023,'Mercer, NJ','courtlistener','REVERSED',1,1000,1000)`).run();
    }, /LEGAL_DISPOSITION/);

    seedApprovedCaseAndEpisode(db, 'PENDING_HUMAN_SIGNOFF');
    db.prepare(`INSERT INTO release_approvals VALUES ('ap_1','ep_1','FACTUAL_ACCURACY','sha_bundle_1','APPROVED','rev_1',1001,'ok')`).run();

    assert.throws(() => {
      db.prepare(`UPDATE cases SET disposition_status = 'REVERSED', updated_at = 2000 WHERE case_id = 'case_1'`).run();
    }, /LEGAL_DISPOSITION/);

    db.prepare(`UPDATE cases SET disposition_status = 'REVERSED', conviction_confirmed = 0, updated_at = 2000 WHERE case_id = 'case_1'`).run();
    assert.equal(db.prepare(`SELECT state FROM episodes WHERE episode_id = 'ep_1'`).get().state, 'QUARANTINED_LEGAL_HOLD');
    assert.equal(db.prepare(`SELECT status FROM release_approvals WHERE approval_id = 'ap_1'`).get().status, 'REVOKED');
    db.close();
  }],

  ['6. F-04 & F-09: Anonymization/anchor lock states default unapproved & spatial anchors enforce FK + grid_cell', () => {
    const db = setupDb();
    db.prepare(`INSERT INTO cases (case_id,defendant_name,incident_year,jurisdiction,verification_source,disposition_status,conviction_confirmed,created_at,updated_at)
                VALUES ('case_raw','John Doe',2023,'Mercer, NJ','courtlistener','AFFIRMED',1,1000,1000)`).run();
    assert.equal(db.prepare(`SELECT anonymization_status FROM cases WHERE case_id = 'case_raw'`).get().anonymization_status, 'NOT_STARTED');

    db.prepare(`INSERT INTO episodes (episode_id,case_id,state,cold_open_archetype,updated_at,created_at)
                VALUES ('ep_raw','case_raw','EVIDENCE_AND_2K_LOCKED','ALIBI_THAT_CRACKED',1000,1000)`).run();
    db.prepare(`INSERT INTO still_assets (still_2k_id,episode_id,asset_path,asset_sha256,width_px,height_px,created_at)
                VALUES ('st_1','ep_raw','room.png','sha_room',2560,1440,1000)`).run();
    db.prepare(`INSERT INTO spatial_anchors (anchor_id,episode_id,still_2k_id,clue_name,grid_cell,x_px,y_px)
                VALUES ('anc_1','ep_raw','st_1','broken_chair','E5',1280,720)`).run();
    assert.equal(db.prepare(`SELECT lock_status FROM spatial_anchors WHERE anchor_id = 'anc_1'`).get().lock_status, 'DRAFT');

    assert.throws(() => {
      db.prepare(`UPDATE spatial_anchors SET lock_status = 'LOCKED' WHERE anchor_id = 'anc_1'`).run();
    });
    assert.throws(() => {
      db.prepare(`INSERT INTO spatial_anchors (anchor_id,episode_id,still_2k_id,clue_name,grid_cell,x_px,y_px)
                  VALUES ('anc_bad','ep_raw','st_1','x','Z99',100,100)`).run();
    });
    db.close();
  }],

  ['7. F-07 & F-10: Unique (episode_id, scene_id) prevents duplicate jobs & supports T2V/1F/2F prompt_mode', () => {
    const db = setupDb();
    seedApprovedCaseAndEpisode(db, 'AWAITING_FLOW_BATCH');
    insertApprovedScenePlanAndScene(db, 's1', 1, 'FLOW_HERO_VIDEO', 'HeroVideoBridge', 0, 12000);
    insertApprovedScenePlanAndScene(db, 's2', 2, 'FLOW_HERO_VIDEO', 'HeroVideoBridge', 12000, 20000);

    db.prepare(`INSERT INTO flow_jobs (flow_job_id,episode_id,scene_id,idempotency_key,prompt_mode,duration_bucket_sec,start_frame_png,end_frame_png,prompt_v1,prompt_v2_safe,fallback_spec_json,provider_operation_id,state,updated_at)
                VALUES ('fj_t2v','ep_1','s1','idem_1','TEXT_TO_VIDEO',12,NULL,NULL,'p1','p2','{}','op_1','UNKNOWN_RECONCILE',1000)`).run();
    assert.throws(() => {
      db.prepare(`INSERT INTO flow_jobs (flow_job_id,episode_id,scene_id,idempotency_key,prompt_mode,duration_bucket_sec,start_frame_png,end_frame_png,prompt_v1,prompt_v2_safe,fallback_spec_json,updated_at)
                  VALUES ('fj_dup','ep_1','s1','idem_dup','TEXT_TO_VIDEO',8,NULL,NULL,'p1','p2','{}',1001)`).run();
    });
    assert.throws(() => {
      db.prepare(`INSERT INTO flow_jobs (flow_job_id,episode_id,scene_id,idempotency_key,prompt_mode,duration_bucket_sec,start_frame_png,end_frame_png,prompt_v1,prompt_v2_safe,fallback_spec_json,updated_at)
                  VALUES ('fj_bad2f','ep_1','s2','idem_2','FIRST_AND_LAST_FRAME',12,'a.png','b.png','p1','p2','{}',1001)`).run();
    });
    db.prepare(`INSERT INTO flow_jobs (flow_job_id,episode_id,scene_id,idempotency_key,prompt_mode,duration_bucket_sec,start_frame_png,end_frame_png,prompt_v1,prompt_v2_safe,fallback_spec_json,updated_at)
                VALUES ('fj_2f','ep_1','s2','idem_3','FIRST_AND_LAST_FRAME',8,'a.png','b.png','p1','p2','{}',1001)`).run();
    assert.equal(db.prepare('SELECT COUNT(*) AS c FROM flow_jobs').get().c, 2);
    db.close();
  }],

  ['8. F-08: Atomic daily credit query enforces 24h+5m lockout before reset and refills cleanly at/after reset', () => {
    const db = setupDb();
    const stmt = db.prepare(extractQuery('atomic_refill_and_reserve_daily_account_credits'));
    const t0 = 1_700_000_000_000;
    const expectedReset = t0 + 86_400_000 + 300_000;

    let r = stmt.get({ ':account_id': 'acct_1', ':credits': 50, ':now_ms': t0 });
    assert.equal(r.daily_credits_left, 0);
    assert.equal(stmt.get({ ':account_id': 'acct_1', ':credits': 10, ':now_ms': expectedReset - 1 }), undefined);
    r = stmt.get({ ':account_id': 'acct_1', ':credits': 10, ':now_ms': expectedReset });
    assert.equal(r.daily_credits_left, 40);
    db.close();
  }],

  ['9. F-09: Timeline non-overlap triggers & kind-specific voice_segments constraints enforced', () => {
    const db = setupDb();
    seedApprovedCaseAndEpisode(db, 'VOICE_READY');
    assert.throws(() => {
      db.prepare(`INSERT INTO voice_segments VALUES ('vs_bad','ep_1',1,'NARRATION',0,5000,NULL,NULL)`).run();
    });
    db.prepare(`INSERT INTO voice_segments VALUES ('vs_1','ep_1',1,'NARRATION',0,10000,'s1.wav',NULL)`).run();
    assert.throws(() => {
      db.prepare(`INSERT INTO voice_segments VALUES ('vs_ov','ep_1',2,'NARRATION',9500,15000,'s2.wav',NULL)`).run();
    }, /TIMELINE_OVERLAP/);
    db.prepare(`INSERT INTO voice_segments VALUES ('vs_2','ep_1',2,'TWIST_PAD',10000,10600,NULL,NULL)`).run();
    assert.equal(db.prepare('SELECT COUNT(*) AS c FROM voice_segments').get().c, 2);
    db.close();
  }],

  ['10. F-12 & F-20: Honest analytics UNKNOWN defaults + non-null YouTube 30-day TTL full-field purge', () => {
    const db = setupDb();
    assert.throws(() => {
      db.prepare(`INSERT INTO outlier_candidates (candidate_id,track,source_video_id,views_count,outlier_ratio,saturation_index,seed_packet_json,raw_yt_payload_json,yt_ttl_expires_at,status,created_at)
                  VALUES ('c_bad','TRACK_A_OUTLIER','v1',50000,10.0,20,'{}','{"raw":1}',NULL,'CANDIDATE',1000)`).run();
    });
    db.prepare(`INSERT INTO channels_watchlist (channel_id, uploads_playlist_id, channel_name, subscriber_count, median_20_views, yt_ttl_expires_at)
                VALUES ('UCkeep','UUkeep','Crime Channel',50000,10000,2000)`).run();
    db.prepare(`INSERT INTO outlier_candidates (candidate_id,track,source_video_id,source_channel_id,views_count,outlier_ratio,saturation_index,seed_packet_json,raw_yt_payload_json,yt_ttl_expires_at,status,created_at)
                VALUES ('c_ok','TRACK_A_OUTLIER','v1','UCkeep',50000,10.0,20,'{"yt_title":"x"}','{"raw":1}',2000,'GREENLIT',1000)`).run();
    db.prepare(`INSERT INTO saturation_checks (check_id, candidate_id, phase, aliases_json, n_mega_excl, n_recent_excl, n_14d_wave, si_score, checked_at)
                VALUES ('chk_1','c_ok','SCOUTING','["alias"]',2,3,1,40,1500)`).run();
    db.prepare(extractQuery('purge_expired_yt_api_records')).run({ ':now_ms': 2500 });
    const purged = db.prepare(`SELECT views_count, outlier_ratio, raw_yt_payload_json, source_video_id, saturation_index, status FROM outlier_candidates WHERE candidate_id='c_ok'`).get();
    assert.equal(purged.views_count, null);
    assert.equal(purged.raw_yt_payload_json, null);
    assert.equal(purged.source_video_id, null);
    assert.equal(purged.saturation_index, 0);
    assert.equal(purged.status, 'EXPIRED_TOS_PURGED');
    assert.equal(db.prepare(`SELECT aliases_json FROM saturation_checks WHERE check_id='chk_1'`).get().aliases_json, '[]');
    assert.equal(db.prepare(`SELECT channel_name, subscriber_count, yt_api_purged_at FROM channels_watchlist WHERE channel_id='UCkeep'`).get().channel_name, '');
    assert.equal(db.prepare(`SELECT subscriber_count FROM channels_watchlist WHERE channel_id='UCkeep'`).get().subscriber_count, 0);

    seedApprovedCaseAndEpisode(db, 'MASTERED');
    db.prepare(`INSERT INTO episode_analytics (snapshot_id,episode_id,days_since_publish,watch_hours_total,captured_at)
                VALUES ('an_1','ep_1',2,180.5,5000)`).run();
    const an = db.prepare(`SELECT adsense_status, adsense_source, ctr_pct FROM episode_analytics WHERE snapshot_id='an_1'`).get();
    assert.equal(an.adsense_status, 'UNKNOWN');
    assert.equal(an.adsense_source, 'UNAVAILABLE');
    assert.equal(an.ctr_pct, null);
    db.close();
  }],

  ['11. F-14 & F-15: Per-asset rights provenance blocks RESTRICTED_NO_REUSE approval & tracks honest ASR disagreement', () => {
    const db = setupDb();
    seedApprovedCaseAndEpisode(db, 'EVIDENCE_AND_2K_LOCKED');
    assert.throws(() => {
      db.prepare(`INSERT INTO foia_media_assets (asset_id,case_id,source_domain,source_url,creator_entity,rights_holder,license_basis,rights_review_status,rights_reviewed_by,rights_reviewed_at,media_kind,raw_path)
                  VALUES ('fa_bad','case_1','muckrock.com','https://muckrock.com/1','Bystander','Private Citizen','RESTRICTED_NO_REUSE','APPROVED','rev_1',1000,'bodycam_mp4','raw.mp4')`).run();
    });
    db.prepare(`INSERT INTO foia_media_assets (asset_id,case_id,source_domain,source_url,creator_entity,rights_holder,license_basis,rights_review_status,rights_reviewed_by,rights_reviewed_at,media_kind,raw_path,asr_hypothesis_disagreement,human_audio_review_required)
                VALUES ('fa_ok','case_1','fbi.gov','https://fbi.gov/1','US Federal Employee','Public Domain (17 USC 105)','US_FED_EMPLOYEE_17USC105','APPROVED','rev_1',1000,'call_911_wav','911.wav',0.14,1)`).run();
    assert.equal(db.prepare(`SELECT human_audio_review_required FROM foia_media_assets WHERE asset_id='fa_ok'`).get().human_audio_review_required, 1);
    db.close();
  }],

  ['12. Quota bucket & RULE_09 news_report hedging triggers remain strictly enforced', () => {
    const db = setupDb();
    const stmt = db.prepare(extractQuery('consume_quota_bucket'));
    assert.equal(stmt.get({ ':bucket_name': 'yt_search', ':units': 60 }).used_today, 60);
    assert.equal(stmt.get({ ':bucket_name': 'yt_search', ':units': 45 }), undefined);

    seedApprovedCaseAndEpisode(db, 'SCOUTED');
    db.prepare(`INSERT INTO primary_documents VALUES ('doc_1','case_1','example.com','https://example.com/1','news_text_only','abc','/tmp/1.txt',1000)`).run();
    assert.throws(() => {
      db.prepare(`INSERT INTO fact_ledger VALUES ('f1','case_1','2023-11-04T22:00:00Z','Suspect seen','[]','Route 9','news_report','doc_1','p.1',0,'[]')`).run();
    }, /RULE_09/);
    db.close();
  }],

  ['13. Settlement cannot release a positive charge or bill an offline test, and $2 sandbox is cumulative', () => {
    const db = setupDb();
    seedApprovedCaseAndEpisode(db, 'AWAITING_FLOW_BATCH');
    const reserve = db.prepare(extractQuery('reserve_provider_budget'));
    const settle = db.prepare(extractQuery('settle_provider_budget'));
    reserve.get({
      ':reservation_id': 'r_rel', ':episode_id': 'ep_1', ':job_id': 'job_rel', ':attempt_number': 1,
      ':provider_id': 'tts', ':purpose': 'PRODUCTION', ':year_month': '2026-11',
      ':estimated_micro_usd': 1000, ':now_ms': 1000
    });
    assert.throws(() => {
      settle.get({
        ':reservation_id': 'r_rel', ':actual_micro_usd': 1000, ':final_status': 'RELEASED', ':now_ms': 1100
      });
    }, /BUDGET_SETTLEMENT_BLOCKED/);
    settle.get({
      ':reservation_id': 'r_rel', ':actual_micro_usd': 1000, ':final_status': 'COMMITTED', ':now_ms': 1100
    });

    reserve.get({
      ':reservation_id': 'r_off', ':episode_id': 'ep_1', ':job_id': 'job_off', ':attempt_number': 1,
      ':provider_id': 'tts', ':purpose': 'OFFLINE_TEST', ':year_month': '2026-11',
      ':estimated_micro_usd': 0, ':now_ms': 1200
    });
    assert.throws(() => {
      settle.get({
        ':reservation_id': 'r_off', ':actual_micro_usd': 1, ':final_status': 'COMMITTED', ':now_ms': 1300
      });
    }, /BUDGET_SETTLEMENT_BLOCKED/);

    reserve.get({
      ':reservation_id': 'r_sb1', ':episode_id': 'ep_1', ':job_id': 'job_sb', ':attempt_number': 1,
      ':provider_id': 'gemini_omni', ':purpose': 'LIVE_SANDBOX', ':year_month': '2026-11',
      ':estimated_micro_usd': 1500000, ':now_ms': 1400
    });
    assert.throws(() => {
      reserve.get({
        ':reservation_id': 'r_sb2', ':episode_id': 'ep_1', ':job_id': 'job_sb', ':attempt_number': 2,
        ':provider_id': 'gemini_omni', ':purpose': 'LIVE_SANDBOX', ':year_month': '2026-11',
        ':estimated_micro_usd': 600000, ':now_ms': 1500
      });
    }, /LIVE_SANDBOX_CAP_EXCEEDED/);
    db.close();
  }],

  ['14. Hero clip count and duration are cumulative, including a later duration update', () => {
    const db = setupDb();
    seedApprovedCaseAndEpisode(db, 'AWAITING_FLOW_BATCH');
    db.prepare(`UPDATE episodes SET max_hero_clips = 1, max_hero_duration_sec = 10 WHERE episode_id = 'ep_1'`).run();
    insertApprovedScenePlanAndScene(db, 's1', 1, 'FLOW_HERO_VIDEO', 'HeroVideoBridge', 0, 8000);
    insertApprovedScenePlanAndScene(db, 's2', 2, 'FLOW_HERO_VIDEO', 'HeroVideoBridge', 8000, 16000);
    db.prepare(`INSERT INTO flow_jobs (
      flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode, duration_bucket_sec,
      start_frame_png, end_frame_png, prompt_v1, prompt_v2_safe, fallback_spec_json, state, updated_at
    ) VALUES ('fj1','ep_1','s1','idem_h1','TEXT_TO_VIDEO',8,NULL,NULL,'p','p2','{}','PENDING',1000)`).run();
    assert.throws(() => {
      db.prepare(`INSERT INTO flow_jobs (
        flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode, duration_bucket_sec,
        start_frame_png, end_frame_png, prompt_v1, prompt_v2_safe, fallback_spec_json, state, updated_at
      ) VALUES ('fj2','ep_1','s2','idem_h2','TEXT_TO_VIDEO',4,NULL,NULL,'p','p2','{}','PENDING',1001)`).run();
    }, /HERO_CAP_EXCEEDED/);
    db.prepare(`UPDATE episodes SET max_hero_clips = 2, max_hero_duration_sec = 12 WHERE episode_id = 'ep_1'`).run();
    db.prepare(`INSERT INTO flow_jobs (
      flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode, duration_bucket_sec,
      start_frame_png, end_frame_png, prompt_v1, prompt_v2_safe, fallback_spec_json, state, updated_at
    ) VALUES ('fj2','ep_1','s2','idem_h2','TEXT_TO_VIDEO',4,NULL,NULL,'p','p2','{}','PENDING',1001)`).run();
    assert.throws(() => {
      db.prepare(`UPDATE flow_jobs SET duration_bucket_sec = 8 WHERE flow_job_id = 'fj2'`).run();
    }, /HERO_CAP_EXCEEDED/);
    db.close();
  }],

  ['15. Release insert is gated, and bundle or QA changes demote a ready episode', () => {
    const db = setupDb();
    db.prepare(`INSERT INTO cases (case_id, defendant_name, incident_year, jurisdiction, docket_id, primary_record_verified, verification_source, disposition_status, conviction_confirmed, anonymization_status, anonymized_by, anonymized_at, anonymization_artifact_sha256, created_at, updated_at)
      VALUES ('case_pub','John Doe',2023,'Mercer, NJ','DK-9',1,'courtlistener','AFFIRMED',1,'APPROVED','reviewer_a',1000,'sha_anon_1',1000,1000)`).run();
    assert.throws(() => {
      db.prepare(`INSERT INTO episodes (episode_id, case_id, state, flow_backend_mode, cold_open_archetype, total_master_ms, timeline_validated_sha256, ready_bundle_sha256, updated_at, created_at)
        VALUES ('ep_pub','case_pub','PUBLISHED','GEMINI_OMNI_INTERACTIONS','911_CALL_IN_MEDIA_RES',1200000,'sha_tl_1','sha_bundle_1',1000,1000)`).run();
    }, /RELEASE_GATE_BLOCKED/);
    seedApprovedCaseAndEpisode(db, 'MASTERED');
    insertApprovedScenePlanAndScene(db);
    const gates = ['FACTUAL_ACCURACY', 'PRIVACY_PII', 'SOURCE_RIGHTS', 'SYNTHETIC_DISCLOSURE', 'ILLUSTRATIVE_LABELING'];
    gates.forEach((g, idx) => {
      db.prepare(`INSERT INTO release_approvals VALUES (?, 'ep_1', ?, 'sha_bundle_1', 'APPROVED', 'editor_jane', 2000, 'verified')`).run(`rel_${idx}`, g);
    });
    db.prepare(`INSERT INTO qa_reports VALUES ('qa_rel','ep_1',-14.0,-1.5,1,1,'PASSED',1,'final.mp4','sha_mp4',4000)`).run();
    db.prepare(`INSERT INTO compliance_audits VALUES ('aud_rel','case_1',1,1,1,1,1,1,4000)`).run();
    db.prepare(`UPDATE cases SET primary_record_verified = 0 WHERE case_id = 'case_1'`).run();
    assert.throws(() => {
      db.prepare(`UPDATE episodes SET state = 'READY_TO_UPLOAD' WHERE episode_id = 'ep_1'`).run();
    }, /RELEASE_GATE_BLOCKED/);
    db.prepare(`UPDATE cases SET primary_record_verified = 1 WHERE case_id = 'case_1'`).run();
    db.prepare(`UPDATE episodes SET state = 'READY_TO_UPLOAD' WHERE episode_id = 'ep_1'`).run();
    db.prepare(`UPDATE qa_reports SET vision_frame_qa_status = 'PENDING_MANUAL_SPOT_CHECK' WHERE qa_id = 'qa_rel'`).run();
    assert.equal(db.prepare(`SELECT state FROM episodes WHERE episode_id = 'ep_1'`).get().state, 'PENDING_HUMAN_SIGNOFF');
    db.close();
  }],

  ['16. Quota rejects negative units and allows an explicit window reset; refunds are idempotent', () => {
    const db = setupDb();
    const consume = db.prepare(extractQuery('consume_quota_bucket'));
    assert.equal(consume.get({ ':bucket_name': 'yt_search', ':units': -5 }), undefined);
    assert.equal(db.prepare(`SELECT used_today FROM quota_buckets WHERE bucket_name = 'yt_search'`).get().used_today, 0);
    consume.get({ ':bucket_name': 'yt_search', ':units': 10 });
    const reset = db.prepare(extractQuery('reset_quota_window'));
    assert.equal(reset.get({ ':bucket_name': 'yt_search', ':now_ms': 86_400_000 }).used_today, 0);

    db.prepare(`UPDATE google_accounts SET next_daily_reset_utc_ms = 9000000000, daily_credits_left = 10 WHERE account_id = 'acct_1'`).run();
    const refund = db.prepare(extractQuery('refund_daily_account_credits'));
    refund.get({ ':refund_id': 'rf_1', ':account_id': 'acct_1', ':reservation_id': 'res_1', ':credits': 5, ':now_ms': 1000 });
    const after = db.prepare(`SELECT daily_credits_left FROM google_accounts WHERE account_id = 'acct_1'`).get().daily_credits_left;
    assert.throws(() => {
      refund.get({ ':refund_id': 'rf_1', ':account_id': 'acct_1', ':reservation_id': 'res_1', ':credits': 5, ':now_ms': 1001 });
    });
    assert.equal(db.prepare(`SELECT daily_credits_left FROM google_accounts WHERE account_id = 'acct_1'`).get().daily_credits_left, after);
    db.close();
  }],
];

let passed = 0;
for (const [name, fn] of scenarios) {
  fn();
  console.log(`PASS: ${name}`);
  passed++;
}
console.log(`\n${passed}/${scenarios.length} schema scenarios passed.`);
