"""Offline tests for the Track B CourtListener appellate radar."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent1_scout.courtlistener_radar import (
    CACHE_TTL_MS,
    COURTLISTENER_DAILY_CAP,
    MIN_OPINION_WORDS,
    SCOUT_REQUEST_BUDGET,
    SKIP_BELOW_WORD_MINIMUM,
    SKIP_NOT_AFFIRMED,
    SKIP_NOT_APPELLATE,
    SKIP_NOT_CRIMINAL,
    SKIP_PRIMARY_REMANDED,
    SKIP_PRIMARY_REVERSED,
    TRACK_B,
    CourtListenerRadar,
)

NOW_MS = 1_700_000_000_000
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "courtlistener_opinions.json"
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "pipeline.sql"
SEED_KEYS = {
    "contract_version",
    "track",
    "lead_classification",
    "suspect_names",
    "victim_names",
    "incident_date_or_year",
    "county_state",
    "docket_ids",
    "unanswered_comment_questions",
}


class CountingFetcher:
    def __init__(self, opinions: dict[str, dict]) -> None:
        self.opinions = opinions
        self.calls: list[str] = []

    def __call__(self, opinion_id: str) -> dict:
        self.calls.append(opinion_id)
        return self.opinions[opinion_id]


def cache_ddl() -> str:
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    try:
        start = text.index("CREATE TABLE courtlistener_cache")
    except ValueError as exc:
        raise AssertionError("courtlistener_cache missing from schema/pipeline.sql") from exc
    buffer = ""
    for line in text[start:].splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            return buffer.strip()
    raise AssertionError("courtlistener_cache statement is incomplete")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(cache_ddl())
    return connection


def load_fixture() -> dict[str, dict]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["live_http"] is False
    assert payload["daily_cap"] == COURTLISTENER_DAILY_CAP
    assert payload["scout_request_budget"] == SCOUT_REQUEST_BUDGET
    return {str(opinion["id"]): opinion for opinion in payload["opinions"]}


def affirmed_opinion(opinion_id: str, *, words: int = MIN_OPINION_WORDS) -> dict:
    return {
        "id": opinion_id,
        "case_name": f"State v. Person {opinion_id}",
        "defendant": f"Person {opinion_id}",
        "docket_number": f"2020-CR-{opinion_id}",
        "court": "Montana Supreme Court",
        "appellate": True,
        "criminal": True,
        "date_filed": "2022-01-15",
        "incident_year": "2019",
        "county_state": "Lewis and Clark County, MT",
        "word_count": words,
        "dispositions": [
            {
                "count": "first-degree murder",
                "role": "primary",
                "disposition": "AFFIRMED",
            }
        ],
    }


def test_schema_table_is_used_for_cache_rows() -> None:
    ddl = cache_ddl()
    assert "STRICT" in ddl
    assert "WITHOUT ROWID" in ddl
    connection = connect()
    columns = [
        row[1]
        for row in connection.execute("PRAGMA table_info(courtlistener_cache)")
    ]
    assert columns == [
        "cache_key",
        "docket_id",
        "payload_json",
        "fetched_at",
        "expires_at",
    ]


def test_budget_is_half_the_daily_cap_without_rounding_up() -> None:
    assert COURTLISTENER_DAILY_CAP == 125
    assert SCOUT_REQUEST_BUDGET == 62
    assert SCOUT_REQUEST_BUDGET <= COURTLISTENER_DAILY_CAP // 2
    assert COURTLISTENER_DAILY_CAP - SCOUT_REQUEST_BUDGET >= 63


def test_fixture_keeps_affirmed_criminal_appellate_seeds() -> None:
    opinions = load_fixture()
    fetcher = CountingFetcher(opinions)
    radar = CourtListenerRadar(fetcher, connect(), now_ms=NOW_MS)
    result = radar.poll(list(opinions))

    assert result.request_budget == 62
    assert result.requests_used == len(opinions)
    assert result.cache_hits == 0
    assert result.deferred_opinion_ids == ()

    by_id = {seed.opinion_id: seed for seed in result.seeds}
    assert set(by_id) == {"1042001", "1042004", "1042008"}
    assert [seed.opinion_id for seed in result.seeds] == [
        "1042001",
        "1042004",
        "1042008",
    ]

    hale = by_id["1042001"]
    assert hale.mixed_disposition is False
    assert hale.primary_disposition == "AFFIRMED"
    assert hale.word_count == 4200
    assert hale.primary_count == "first-degree murder"
    assert set(hale.seed) == SEED_KEYS
    assert hale.seed["track"] == TRACK_B
    assert hale.seed["lead_classification"] == "LEAD_ONLY"
    assert hale.seed["contract_version"] == "v4"
    assert hale.seed["suspect_names"] == ["John Hale"]
    assert hale.seed["incident_date_or_year"] == "2018"
    assert hale.seed["county_state"] == "Lewis and Clark County, MT"
    assert hale.seed["docket_ids"] == ["2019-CR-1042"]
    assert hale.seed["unanswered_comment_questions"] == []
    assert "mixed_disposition" not in hale.seed

    pell = by_id["1042004"]
    assert pell.mixed_disposition is True
    assert pell.primary_disposition == "AFFIRMED"
    assert pell.primary_count == "first-degree murder"
    assert pell.seed["track"] == TRACK_B
    assert pell.seed["suspect_names"] == ["Andrea Pell"]
    assert "REVERSED" in json.dumps(opinions["1042004"])

    okonkwo = by_id["1042008"]
    assert okonkwo.mixed_disposition is True
    assert okonkwo.primary_count == "armed robbery"
    assert okonkwo.seed["docket_ids"] == ["2016-CR-512"]

    reasons = {skip.opinion_id: skip.reason for skip in result.skipped}
    assert reasons == {
        "1042002": SKIP_PRIMARY_REVERSED,
        "1042003": SKIP_PRIMARY_REMANDED,
        "1042005": SKIP_BELOW_WORD_MINIMUM,
        "1042006": SKIP_NOT_CRIMINAL,
        "1042007": SKIP_PRIMARY_REVERSED,
        "1042009": SKIP_NOT_APPELLATE,
        "1042010": SKIP_NOT_AFFIRMED,
    }


def test_second_poll_reads_courtlistener_cache_without_another_request() -> None:
    opinions = load_fixture()
    fetcher = CountingFetcher(opinions)
    connection = connect()
    first = CourtListenerRadar(fetcher, connection, now_ms=NOW_MS)
    first_result = first.poll(["1042001", "1042004"])
    assert first_result.requests_used == 2

    rows = connection.execute(
        """
        SELECT cache_key, docket_id, payload_json, fetched_at, expires_at
        FROM courtlistener_cache
        ORDER BY cache_key
        """
    ).fetchall()
    assert [row[0] for row in rows] == ["1042001", "1042004"]
    hale_row = rows[0]
    assert hale_row[1] == "2019-CR-1042"
    stored = json.loads(hale_row[2])
    assert stored["id"] == 1042001
    assert stored["defendant"] == "John Hale"
    assert hale_row[3] == NOW_MS
    assert hale_row[4] == NOW_MS + CACHE_TTL_MS

    second_fetcher = CountingFetcher(opinions)
    second = CourtListenerRadar(second_fetcher, connection, now_ms=NOW_MS)
    second_result = second.poll(["1042004", "1042001"])
    assert second_fetcher.calls == []
    assert second_result.requests_used == 0
    assert second_result.cache_hits == 2
    assert [seed.opinion_id for seed in second_result.seeds] == ["1042004", "1042001"]
    assert second_result.seeds[0].mixed_disposition is True
    assert second_result.seeds[1].mixed_disposition is False
    assert second.requests_used == 0


def test_prewritten_cache_row_satisfies_poll_without_fetch() -> None:
    payload = affirmed_opinion("555")
    connection = connect()
    connection.execute(
        """
        INSERT INTO courtlistener_cache (
            cache_key, docket_id, payload_json, fetched_at, expires_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            "555",
            "2020-CR-555",
            json.dumps(payload),
            NOW_MS,
            NOW_MS + CACHE_TTL_MS,
        ),
    )
    connection.commit()

    def forbidden(opinion_id: str) -> dict:
        raise AssertionError(f"fetcher called for {opinion_id}")

    result = CourtListenerRadar(forbidden, connection, now_ms=NOW_MS).poll(["555"])
    assert result.requests_used == 0
    assert result.cache_hits == 1
    assert result.seeds[0].seed["track"] == TRACK_B
    assert result.seeds[0].mixed_disposition is False
    assert result.seeds[0].seed["docket_ids"] == ["2020-CR-555"]


def test_expired_cache_row_spends_one_refetch() -> None:
    opinions = {"555": affirmed_opinion("555")}
    connection = connect()
    fetcher = CountingFetcher(opinions)
    CourtListenerRadar(fetcher, connection, now_ms=NOW_MS).poll(["555"])
    connection.execute(
        "UPDATE courtlistener_cache SET expires_at = ? WHERE cache_key = ?",
        (NOW_MS - 1, "555"),
    )
    connection.commit()
    again = CountingFetcher(opinions)
    result = CourtListenerRadar(again, connection, now_ms=NOW_MS).poll(["555"])
    assert again.calls == ["555"]
    assert result.requests_used == 1
    assert result.cache_hits == 0
    assert result.seeds[0].opinion_id == "555"


def test_poller_stops_at_62_requests_and_keeps_the_cap_across_polls() -> None:
    opinions = {str(index): affirmed_opinion(str(index)) for index in range(1, 64)}
    fetcher = CountingFetcher(opinions)
    connection = connect()
    radar = CourtListenerRadar(fetcher, connection, now_ms=NOW_MS)
    ids = [str(index) for index in range(1, 64)]
    result = radar.poll(ids)
    assert result.requests_used == 62
    assert fetcher.calls == ids[:62]
    assert result.deferred_opinion_ids == ("63",)
    assert len(result.seeds) == 62
    assert radar.requests_used == 62

    calls_after_first = list(fetcher.calls)
    follow_up = radar.poll(["1", "63", "64"])
    assert fetcher.calls == calls_after_first
    assert follow_up.requests_used == 0
    assert follow_up.cache_hits == 1
    assert follow_up.deferred_opinion_ids == ("63", "64")
    assert [seed.opinion_id for seed in follow_up.seeds] == ["1"]

    fresh_fetcher = CountingFetcher(opinions)
    fresh = CourtListenerRadar(fresh_fetcher, connection, now_ms=NOW_MS)
    resumed = fresh.poll(["63"])
    assert fresh_fetcher.calls == ["63"]
    assert resumed.requests_used == 1
    assert resumed.seeds[0].seed["track"] == TRACK_B


def test_duplicate_ids_fetch_once() -> None:
    fetcher = CountingFetcher({"1042001": load_fixture()["1042001"]})
    result = CourtListenerRadar(fetcher, connect(), now_ms=NOW_MS).poll(
        ["1042001", "1042001"]
    )
    assert fetcher.calls == ["1042001"]
    assert result.requests_used == 1
    assert len(result.seeds) == 1


def test_word_count_boundary_uses_plain_text_when_field_absent() -> None:
    short = affirmed_opinion("s", words=2999)
    exact = affirmed_opinion("e", words=3000)
    prose = affirmed_opinion("p")
    del prose["word_count"]
    prose["plain_text"] = " ".join(["affirmed"] * 3000)
    almost = affirmed_opinion("a")
    del almost["word_count"]
    almost["plain_text"] = " ".join(["affirmed"] * 2999)
    opinions = {"s": short, "e": exact, "p": prose, "a": almost}
    result = CourtListenerRadar(
        CountingFetcher(opinions), connect(), now_ms=NOW_MS
    ).poll(["s", "e", "p", "a"])
    assert [seed.opinion_id for seed in result.seeds] == ["e", "p"]
    assert result.seeds[0].word_count == 3000
    assert result.seeds[1].word_count == 3000
    reasons = {skip.opinion_id: skip.reason for skip in result.skipped}
    assert reasons == {"s": SKIP_BELOW_WORD_MINIMUM, "a": SKIP_BELOW_WORD_MINIMUM}


def test_minor_remand_does_not_set_mixed_or_reject() -> None:
    opinion = affirmed_opinion("r")
    opinion["dispositions"] = [
        {"count": "first-degree murder", "role": "primary", "disposition": "AFFIRMED"},
        {"count": "sentencing claim", "role": "minor", "disposition": "REMANDED"},
    ]
    result = CourtListenerRadar(
        CountingFetcher({"r": opinion}), connect(), now_ms=NOW_MS
    ).poll(["r"])
    assert len(result.seeds) == 1
    assert result.seeds[0].mixed_disposition is False
    assert result.skipped == ()


def test_misleading_reversed_label_does_not_override_affirmed_murder() -> None:
    opinion = affirmed_opinion("trap")
    opinion["primary_disposition"] = "REVERSED"
    opinion["disposition_summary"] = "REVERSED"
    opinion["plain_text"] = "REVERSED appears in the syllabus only."
    opinion["dispositions"] = [
        {"count": "theft", "role": "minor", "disposition": "REVERSED"},
        {"count": "first-degree murder", "disposition": "AFFIRMED"},
    ]
    result = CourtListenerRadar(
        CountingFetcher({"trap": opinion}), connect(), now_ms=NOW_MS
    ).poll(["trap"])
    assert result.skipped == ()
    assert result.seeds[0].mixed_disposition is True
    assert result.seeds[0].primary_disposition == "AFFIRMED"
    assert result.seeds[0].primary_count == "first-degree murder"


def test_scalar_reversed_without_counts_is_skipped() -> None:
    opinion = affirmed_opinion("scalar")
    del opinion["dispositions"]
    opinion["primary_disposition"] = "REVERSED"
    result = CourtListenerRadar(
        CountingFetcher({"scalar": opinion}), connect(), now_ms=NOW_MS
    ).poll(["scalar"])
    assert result.seeds == ()
    assert result.skipped[0].reason == SKIP_PRIMARY_REVERSED
