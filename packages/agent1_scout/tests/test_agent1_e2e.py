"""Offline Agent 1 trap suite. Fixtures only. No network."""

from __future__ import annotations

import json
from pathlib import Path

from agent1_scout.pipeline import (
    ABORTED_COPYCAT_WAVE,
    FINISH,
    KILL_90D,
    TRACK_B,
    Agent1ScoutService,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SERVICE = Agent1ScoutService(FIXTURES)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_nightly_poll_uses_zero_search_list() -> None:
    fixture = _load("nightly_poll.json")
    trap_ids = {item["video_id"] for item in fixture["search_list_trap"]["items"]}
    result = SERVICE.nightly_poll()

    assert result.search_list_calls == 0
    assert "search.list" not in result.methods
    assert "playlistItems.list" in result.methods
    assert "videos.list" in result.methods
    assert "vid-long-affidavit" in result.video_ids
    assert "vid-short-clip" not in result.video_ids
    assert trap_ids.isdisjoint(result.video_ids)


def test_five_day_600k_video_is_counted_in_one_si_bucket() -> None:
    report = SERVICE.score_saturation("si_five_day_600k.json")
    score = report.scores[0]

    assert score.video_id == "five-day-600k"
    assert score.views == 600_000
    assert score.age_days == 5
    assert score.buckets == ("N_14d_excl",)
    assert report.counts == {
        "N_14d_excl": 1,
        "N_mega_excl": 0,
        "N_recent_excl": 0,
    }
    assert sum(report.counts.values()) == 1


def test_any_video_over_200k_views_in_90_days_is_instant_kill() -> None:
    report = SERVICE.score_saturation("instant_kill_90d.json")
    killed = {score.video_id for score in report.scores if score.hard_kill}
    reasons = {score.kill_reason for score in report.scores if score.hard_kill}

    assert killed == {
        "five-day-600k",
        "forty-day-250k",
        "ninety-day-200001",
    }
    assert reasons == {KILL_90D}
    assert "ten-day-200000" not in killed
    assert "ninety-one-day-900k" not in killed


def test_age_restricted_xray_falls_back_to_metadata_without_downloads() -> None:
    fixture = _load("age_restricted_xray.json")
    fetched: list[str] = []
    result = SERVICE.inspect_xray(download=fetched.append)

    assert result.fallback == "authorized_metadata"
    assert result.playback == "PLAYBACK_RESTRICTED"
    assert result.lead_classification == "LEAD_ONLY"
    assert result.title == fixture["metadata"]["title"]
    assert result.description == fixture["metadata"]["description"]
    assert result.tags == tuple(fixture["metadata"]["tags"])
    assert result.comment_leads == tuple(fixture["comments"])
    assert result.caption_downloads == 0
    assert result.mp4_downloads == 0
    assert "captions.download" not in result.methods
    assert "mp4" not in result.methods
    assert fetched == []
    assert fixture["mp4_url"] not in result.description


def test_clean_room_deletes_transcript_buffer() -> None:
    fixture = _load("clean_room.json")
    transcript = fixture["transcript"]
    buffer = bytearray(transcript.encode("utf-8"))

    assert len(buffer) > 0
    packet = SERVICE.clean_room(buffer)

    assert buffer == bytearray()
    assert transcript not in json.dumps(packet)
    assert "transcript" not in packet
    assert packet["lead_classification"] == "LEAD_ONLY"
    assert packet["suspect_names"] == fixture["leads"]["suspect_names"]
    assert packet["docket_ids"] == fixture["leads"]["docket_ids"]
    assert packet["unanswered_comment_questions"] == fixture["leads"]["unanswered_comment_questions"]


def test_tabloid_title_fails_safe_title_check() -> None:
    fixture = _load("tabloid_title.json")

    assert SERVICE.safe_title_ctr_ok(fixture["tabloid_title"]) == 0
    assert SERVICE.safe_title_ctr_ok(fixture["documentary_title"]) == 1


def test_payload_older_than_30_days_is_purged() -> None:
    purged = SERVICE.purge_expired_payloads()
    stale = purged["stale-payload"]
    fresh = purged["fresh-payload"]

    assert stale.age_days > 30
    assert stale.status == "EXPIRED_TOS_PURGED"
    assert stale.raw_yt_payload_json is None
    assert stale.views_count is None
    assert stale.outlier_ratio is None
    assert "yt_title" not in stale.seed_packet_json
    assert "yt_description" not in stale.seed_packet_json
    assert stale.seed_packet_json["docket_ids"] == ["2019-CR-44"]

    assert fresh.age_days < 30
    assert fresh.status == "CANDIDATE"
    assert fresh.views_count == 48000
    assert fresh.seed_packet_json["yt_title"] == "What the affidavit leaves open"


def test_sunk_cost_recheck_aborts_day2_and_finishes_four_copycats() -> None:
    fixture = _load("sunk_cost.json")
    by_id = {row.scenario_id: row for row in SERVICE.recheck_sunk_cost()}
    day2 = by_id["day2_wave_20pct"]
    sunk = by_id["sunk_75pct_four_copycats"]
    sunk_fixture = fixture["scenarios"][1]

    assert day2.shift_day == 2
    assert day2.spent_credits_pct == 0.2
    assert day2.n_14d_wave > 3
    assert day2.decision == ABORTED_COPYCAT_WAVE
    assert day2.sunk_cost_override == 0

    assert sunk.spent_credits_pct == 0.75
    assert sunk.n_14d_wave == 4
    assert len(sunk_fixture["copycats"]) == 4
    assert all(item["channel_tier"] == "small" for item in sunk_fixture["copycats"])
    assert sunk.decision == FINISH
    assert sunk.sunk_cost_override == 1


def test_track_b_foia_winners_when_every_track_a_candidate_is_killed() -> None:
    fixture = _load("track_b_fallback.json")
    result = SERVICE.scout()

    assert result.track_a_survivors == ()
    assert result.track_a_killed == tuple(
        row["candidate_id"] for row in fixture["track_a"]
    )
    assert [winner.candidate_id for winner in result.winners] == [
        "foia-completed",
        "cl-affirmed",
    ]
    assert {winner.track for winner in result.winners} == {TRACK_B}
    assert "foia-denial-only" not in {winner.candidate_id for winner in result.winners}
