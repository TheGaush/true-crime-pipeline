# Part 1 Standalone Certification Report

Generated: 2026-11-23T21:50:51Z

## Verdict

**Part 1 is certified only if every check passes.** Any single failure blocks merge readiness for Tasks 193–200.

- **Certified:** YES
- **Total API spend:** `$0.00`
- **Episodes exercised:** 3

## Episodes

### `ep_cert_gemini_01` (GEMINI_OMNI_INTERACTIONS) — PASS
- Spend: `$0.00`

- [PASS] `flow.gemini_omni_interactions` — Episode uses GEMINI_OMNI_INTERACTIONS transport mock: flow_backend_mode=GEMINI_OMNI_INTERACTIONS
- [PASS] `disposition.affirmed_passes` — Affirmed standing conviction clears scout gate: disposition=AFFIRMED
- [PASS] `compliance.anonymization_explicit` — Anonymization never auto-approves; explicit APPROVED required: default=NOT_STARTED explicit_fields_present=True
- [PASS] `evidence.2k_illustrative_locked` — 2K plate is illustrative and LOCKED: lock_status=LOCKED
- [PASS] `gatekeeper.ring_restricted` — Ring / private CCTV marked RESTRICTED_NO_REUSE: reuse_status=RESTRICTED_NO_REUSE
- [PASS] `gatekeeper.8khz_no_demucs` — 8 kHz narrowband speech skips Demucs: rate=8000 demucs=False
- [PASS] `director.plan_before_voice` — ScenePlan PLAN_APPROVED before voice synthesis: plan_status=PLAN_APPROVED voice_started=False
- [PASS] `voice_sync.past_foia_slot` — WhisperX word times sit after FOIA audio slot: foia_slot_end_ms=42000 first_word_ms=44000
- [PASS] `director.hero_limits` — Hero clips <= 10 and each <= 80s: clips=10 durations_sec=[10, 10, 10, 10, 10, 10, 10, 10, 8, 12]
- [PASS] `orchestrator.stub_zero_spend` — RenderBackendStub returns $0.00 OFFLINE_TEST spend: purpose=OFFLINE_TEST micro_usd=0

### `ep_cert_affirmed_02` (GEMINI_OMNI_INTERACTIONS) — PASS
- Spend: `$0.00`

- [PASS] `flow.gemini_omni_interactions` — Episode uses GEMINI_OMNI_INTERACTIONS transport mock: flow_backend_mode=GEMINI_OMNI_INTERACTIONS
- [PASS] `disposition.affirmed_passes` — Affirmed standing conviction clears scout gate: disposition=AFFIRMED
- [PASS] `compliance.anonymization_explicit` — Anonymization never auto-approves; explicit APPROVED required: default=NOT_STARTED explicit_fields_present=True
- [PASS] `evidence.2k_illustrative_locked` — 2K plate is illustrative and LOCKED: lock_status=LOCKED
- [PASS] `gatekeeper.ring_restricted` — Ring / private CCTV marked RESTRICTED_NO_REUSE: reuse_status=RESTRICTED_NO_REUSE
- [PASS] `gatekeeper.8khz_no_demucs` — 8 kHz narrowband speech skips Demucs: rate=8000 demucs=False
- [PASS] `director.plan_before_voice` — ScenePlan PLAN_APPROVED before voice synthesis: plan_status=PLAN_APPROVED voice_started=False
- [PASS] `voice_sync.past_foia_slot` — WhisperX word times sit after FOIA audio slot: foia_slot_end_ms=42000 first_word_ms=44000
- [PASS] `director.hero_limits` — Hero clips <= 10 and each <= 80s: clips=10 durations_sec=[10, 10, 10, 10, 10, 10, 10, 10, 8, 12]
- [PASS] `orchestrator.stub_zero_spend` — RenderBackendStub returns $0.00 OFFLINE_TEST spend: purpose=OFFLINE_TEST micro_usd=0

### `ep_cert_batch_03` (HUMAN_BATCH_DESK) — PASS
- Spend: `$0.00`

- [PASS] `flow.human_batch_desk` — Episode queued on HUMAN_BATCH_DESK backend: flow_backend_mode=HUMAN_BATCH_DESK
- [PASS] `conveyor.batch_desk_park` — HUMAN_BATCH_DESK parks at most 3 episodes FIFO: parked=3 max=3
- [PASS] `disposition.affirmed_passes` — Affirmed standing conviction clears scout gate: disposition=AFFIRMED
- [PASS] `compliance.anonymization_explicit` — Anonymization never auto-approves; explicit APPROVED required: default=NOT_STARTED explicit_fields_present=True
- [PASS] `evidence.2k_illustrative_locked` — 2K plate is illustrative and LOCKED: lock_status=LOCKED
- [PASS] `gatekeeper.ring_restricted` — Ring / private CCTV marked RESTRICTED_NO_REUSE: reuse_status=RESTRICTED_NO_REUSE
- [PASS] `gatekeeper.8khz_no_demucs` — 8 kHz narrowband speech skips Demucs: rate=8000 demucs=False
- [PASS] `director.plan_before_voice` — ScenePlan PLAN_APPROVED before voice synthesis: plan_status=PLAN_APPROVED voice_started=False
- [PASS] `voice_sync.past_foia_slot` — WhisperX word times sit after FOIA audio slot: foia_slot_end_ms=42000 first_word_ms=44000
- [PASS] `director.hero_limits` — Hero clips <= 10 and each <= 80s: clips=10 durations_sec=[10, 10, 10, 10, 10, 10, 10, 10, 8, 12]
- [PASS] `orchestrator.stub_zero_spend` — RenderBackendStub returns $0.00 OFFLINE_TEST spend: purpose=OFFLINE_TEST micro_usd=0

## Global gates

- [PASS] `disposition.reversed_killed` — Reversed conviction quarantines downstream episodes: disposition=REVERSED episode_state=QUARANTINED_LEGAL_HOLD

## Summary table

| check_id | status |
| --- | --- |
| `flow.gemini_omni_interactions` | PASS |
| `disposition.affirmed_passes` | PASS |
| `compliance.anonymization_explicit` | PASS |
| `evidence.2k_illustrative_locked` | PASS |
| `gatekeeper.ring_restricted` | PASS |
| `gatekeeper.8khz_no_demucs` | PASS |
| `director.plan_before_voice` | PASS |
| `voice_sync.past_foia_slot` | PASS |
| `director.hero_limits` | PASS |
| `orchestrator.stub_zero_spend` | PASS |
| `flow.gemini_omni_interactions` | PASS |
| `disposition.affirmed_passes` | PASS |
| `compliance.anonymization_explicit` | PASS |
| `evidence.2k_illustrative_locked` | PASS |
| `gatekeeper.ring_restricted` | PASS |
| `gatekeeper.8khz_no_demucs` | PASS |
| `director.plan_before_voice` | PASS |
| `voice_sync.past_foia_slot` | PASS |
| `director.hero_limits` | PASS |
| `orchestrator.stub_zero_spend` | PASS |
| `flow.human_batch_desk` | PASS |
| `conveyor.batch_desk_park` | PASS |
| `disposition.affirmed_passes` | PASS |
| `compliance.anonymization_explicit` | PASS |
| `evidence.2k_illustrative_locked` | PASS |
| `gatekeeper.ring_restricted` | PASS |
| `gatekeeper.8khz_no_demucs` | PASS |
| `director.plan_before_voice` | PASS |
| `voice_sync.past_foia_slot` | PASS |
| `director.hero_limits` | PASS |
| `orchestrator.stub_zero_spend` | PASS |
| `disposition.reversed_killed` | PASS |

**Checks passed:** 32/32

Part 1 (Developer A) is **certified** for offline vertical slice readiness at $0.00 API spend.