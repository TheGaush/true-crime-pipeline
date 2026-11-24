# 10-episode economics audit

Offline. No provider was called. Month key `2026-11`, the month seeded in `schema/pipeline.sql`.

Runtime split that the ledger is built around: 780s code/FOIA + 340s illustrative stills + 80s hero clips = 1,200s. Hero clips stay at 10.

A solvable month at the conservative cache rate is 10 episodes times $9.60 of video ($96.00) plus $38.00 of chat ($134.00). That is inside the $135.00 all-provider ceiling and inside the $104.00 video ceiling.

The two ceilings cannot be spent together. $38.00 of chat plus $98.00 of video is $136.00, and `trg_provider_global_budget_cap_guard` rejects it. A positive `OFFLINE_TEST` reservation is rejected by `trg_offline_test_zero_spend_guard`.

TC-Task-ID: 199
TC-Track: integration
TC-Never-Merge: true
