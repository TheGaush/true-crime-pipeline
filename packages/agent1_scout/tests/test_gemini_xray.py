"""Offline fakes for agentic playback and the age-restricted metadata fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent1_scout.gemini_xray import (
    CONTRACT_ID,
    GeminiYouTubeXRayClient,
    Mp4DownloadForbidden,
    TooManyYouTubeUrls,
    UnsupportedCaptionsDownload,
    default_providers_yaml,
    load_youtube_xray_model_id,
)

WATCH = "https://www.youtube.com/watch?v=abcdefghijk"
VIDEO_ID = "abcdefghijk"


class FakeGemini:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.download_mp4_calls = 0

    def inspect_youtube_urls(self, *, model, urls):
        assert len(urls) <= 5
        self.calls.append({"model": model, "urls": list(urls)})
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    def download_mp4(self, *args, **kwargs):
        self.download_mp4_calls += 1
        raise AssertionError("MP4 download is not part of the x-ray")


class _Videos:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class _CommentThreads:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class _SpyCaptions:
    def __init__(self):
        self.calls = 0

    def download(self, *args, **kwargs):
        self.calls += 1
        return b"captions"


class FakeYouTube:
    def __init__(self, video, comments):
        self.videos = _Videos(video)
        self.commentThreads = _CommentThreads(comments)
        self.captions = _SpyCaptions()


class AgeGated(Exception):
    def __init__(self):
        super().__init__("AGE_GATED")
        self.code = "AGE_GATED"


def _providers(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "providers.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _client(gemini, youtube, providers: Path) -> GeminiYouTubeXRayClient:
    return GeminiYouTubeXRayClient(gemini, youtube, providers_path=providers)


def _gemini_family_yaml() -> str:
    return """
providers:
  deepseek_chat:
    models:
      - id: not-the-gemini-family
        roles: [youtube_xray]
  gemini_image:
    model_id: gemini-image
  gemini_text:
    models:
      - id: loaded-from-gemini-family
        roles: [youtube_xray]
      - id: later-gemini-model
        roles: [youtube_xray]
    price_usd: null
"""


def _factual_payload():
    return {
        "status": "OK",
        "lead_keys": {
            "suspect_names": ["Ada Lovelace"],
            "victim_names": ["Charles Babbage"],
            "incident_date_or_year": "1843",
            "county_state": "King County, WA",
            "docket_ids": ["1843-CR-001"],
            "unanswered_comment_questions": [],
        },
    }


def test_model_id_is_the_first_gemini_family_youtube_xray_entry(tmp_path: Path) -> None:
    providers = _providers(tmp_path, _gemini_family_yaml())
    client = _client(FakeGemini(_factual_payload()), FakeYouTube({}, {}), providers)
    assert client.model_id == "loaded-from-gemini-family"
    assert client.model_id == load_youtube_xray_model_id(providers)
    assert "not-the-gemini-family" != client.model_id
    assert client.CONTRACT_ID == CONTRACT_ID == "youtube-xray@2"


def test_repo_providers_yaml_supplies_the_gemini_family_model() -> None:
    path = default_providers_yaml()
    model_id = load_youtube_xray_model_id(path)
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert f"id: {model_id}" in text
    assert "youtube_xray" in text
    gemini_at = text.find("\n  gemini_text:")
    chosen_at = text.find(f"id: {model_id}")
    assert gemini_at != -1 and chosen_at > gemini_at
    client = GeminiYouTubeXRayClient(
        FakeGemini(_factual_payload()),
        FakeYouTube({}, {}),
        providers_path=path,
    )
    assert client.model_id == model_id


def test_successful_playback_returns_factual_leads_in_agentic_video_mode(tmp_path: Path) -> None:
    gemini = FakeGemini(_factual_payload())
    youtube = FakeYouTube(
        {"items": [{"snippet": {"title": "unused", "description": "unused", "tags": []}}]},
        {"items": []},
    )
    client = _client(gemini, youtube, _providers(tmp_path, _gemini_family_yaml()))
    results = client.inspect([WATCH])
    assert len(results) == 1
    result = results[0]
    assert result.source_mode == "AGENTIC_VIDEO"
    assert result.lead_classification == "FACTUAL"
    assert result.facts_confirmed is True
    assert result.lead_keys == _factual_payload()["lead_keys"]
    assert result.mp4_downloaded is False
    assert result.authorized_metadata is None
    assert result.public_comment_questions == []
    assert result.contract_id == "youtube-xray@2"
    assert gemini.calls == [{"model": "loaded-from-gemini-family", "urls": [WATCH]}]
    assert gemini.download_mp4_calls == 0
    assert youtube.videos.calls == []
    assert youtube.commentThreads.calls == []
    assert youtube.captions.calls == 0


def test_playback_restricted_uses_authorized_metadata_and_public_questions(tmp_path: Path) -> None:
    gemini = FakeGemini({"status": "PLAYBACK_RESTRICTED"})
    youtube = FakeYouTube(
        {
            "items": [
                {
                    "id": VIDEO_ID,
                    "statistics": {"viewCount": "99"},
                    "snippet": {
                        "title": "County filing",
                        "description": (
                            "suspect: Ada Lovelace; victim: Charles Babbage; "
                            "incident_date_or_year: 1843; county_state: King County, WA; "
                            "docket: 1843-CR-001"
                        ),
                        "tags": ["court-record"],
                        "channelTitle": "Channel Name Leak",
                    },
                }
            ]
        },
        {
            "items": [
                {
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "authorDisplayName": "Casey Commenter",
                                "authorChannelId": {"value": "UC-secret"},
                                "textOriginal": "Contact casey.secret@example.com. Who signed the affidavit?",
                            }
                        }
                    }
                }
            ]
        },
    )
    client = _client(gemini, youtube, _providers(tmp_path, _gemini_family_yaml()))
    result = client.inspect(
        [WATCH],
        search_snippets=["suspect: Snippet Must Not Override"],
    )[0]
    assert result.source_mode == "LEAD_ONLY"
    assert result.lead_classification == "LEAD_ONLY"
    assert result.playback_block == "PLAYBACK_RESTRICTED"
    assert result.facts_confirmed is False
    assert result.comments_are_confirmed_facts is False
    assert result.metadata_is_confirmed_facts is False
    assert result.mp4_downloaded is False
    assert result.authorized_metadata == {
        "title": "County filing",
        "description": (
            "suspect: Ada Lovelace; victim: Charles Babbage; "
            "incident_date_or_year: 1843; county_state: King County, WA; "
            "docket: 1843-CR-001"
        ),
        "tags": ["court-record"],
    }
    assert set(result.authorized_metadata) == {"title", "description", "tags"}
    assert result.lead_keys["suspect_names"] == ["Ada Lovelace"]
    assert "Snippet Must Not Override" not in result.lead_keys["suspect_names"]
    assert result.lead_keys["victim_names"] == ["Charles Babbage"]
    assert result.lead_keys["incident_date_or_year"] == "1843"
    assert result.lead_keys["county_state"] == "King County, WA"
    assert result.lead_keys["docket_ids"] == ["1843-CR-001"]
    assert result.public_comment_questions == ["Who signed the affidavit?"]
    assert result.lead_keys["unanswered_comment_questions"] == ["Who signed the affidavit?"]
    dumped = str(result.as_dict())
    assert "Casey Commenter" not in dumped
    assert "casey.secret@example.com" not in dumped
    assert "Channel Name Leak" not in dumped
    assert "viewCount" not in dumped
    assert youtube.videos.calls == [
        {
            "part": "snippet",
            "id": VIDEO_ID,
            "fields": "items(snippet(title,description,tags))",
        }
    ]
    assert youtube.commentThreads.calls == [
        {
            "part": "snippet",
            "videoId": VIDEO_ID,
            "textFormat": "plainText",
            "maxResults": 20,
        }
    ]
    assert youtube.captions.calls == 0
    assert gemini.download_mp4_calls == 0


def test_age_gated_exception_is_lead_only_and_not_confirmed(tmp_path: Path) -> None:
    gemini = FakeGemini(AgeGated())
    youtube = FakeYouTube(
        {
            "items": [
                {
                    "snippet": {
                        "title": "Age gated",
                        "description": "suspect: Ada Lovelace; year: 1843",
                        "tags": ["county_state: King County, WA"],
                    }
                }
            ]
        },
        {"items": [{"text": "Was the warrant sealed?"}]},
    )
    client = _client(gemini, youtube, _providers(tmp_path, _gemini_family_yaml()))
    result = client.inspect([WATCH])[0]
    assert result.playback_block == "AGE_GATED"
    assert result.source_mode == "LEAD_ONLY"
    assert result.lead_classification == "LEAD_ONLY"
    assert result.facts_confirmed is False
    assert result.comments_are_confirmed_facts is False
    assert result.metadata_is_confirmed_facts is False
    assert result.lead_keys["suspect_names"] == ["Ada Lovelace"]
    assert result.lead_keys["incident_date_or_year"] == "1843"
    assert result.lead_keys["county_state"] == "King County, WA"
    assert result.public_comment_questions == ["Was the warrant sealed?"]
    assert youtube.captions.calls == 0


def test_empty_description_fills_seed_keys_from_comments_and_snippets(tmp_path: Path) -> None:
    gemini = FakeGemini({"error": {"status": "AGE_GATED"}})
    youtube = FakeYouTube(
        {
            "items": [
                {
                    "snippet": {
                        "title": "Do Not Use This Title As A Name",
                        "description": "   ",
                        "tags": ["ignore-tag"],
                        "channelTitle": "Hidden Channel",
                    }
                }
            ]
        },
        {
            "items": [
                {
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "authorDisplayName": "Casey Commenter",
                                "textOriginal": "Which docket was filed?",
                                "entity_mentions": {
                                    "suspect_names": ["Ada Lovelace"],
                                    "docket_ids": ["1843-CR-001"],
                                },
                            }
                        }
                    }
                }
            ]
        },
    )
    client = _client(gemini, youtube, _providers(tmp_path, _gemini_family_yaml()))
    result = client.inspect(
        [f"https://youtu.be/{VIDEO_ID}"],
        search_snippets=[
            "victim: Charles Babbage; county_state: King County, WA; incident_date_or_year: 1843"
        ],
    )[0]
    assert result.video_id == VIDEO_ID
    assert result.source_mode == "LEAD_ONLY"
    assert result.lead_classification == "LEAD_ONLY"
    assert result.facts_confirmed is False
    assert result.comments_are_confirmed_facts is False
    assert result.metadata_is_confirmed_facts is False
    assert result.authorized_metadata["description"] == ""
    assert result.lead_keys == {
        "suspect_names": ["Ada Lovelace"],
        "victim_names": ["Charles Babbage"],
        "incident_date_or_year": "1843",
        "county_state": "King County, WA",
        "docket_ids": ["1843-CR-001"],
        "unanswered_comment_questions": ["Which docket was filed?"],
    }
    dumped = str(result.as_dict())
    assert "Do Not Use This Title As A Name" not in result.lead_keys["suspect_names"]
    assert "ignore-tag" not in result.lead_keys["docket_ids"]
    assert "Casey Commenter" not in dumped
    assert "Hidden Channel" not in dumped
    assert result.mp4_downloaded is False


def test_at_most_five_urls_are_sent_and_a_sixth_never_calls_gemini(tmp_path: Path) -> None:
    ids = [f"{index:011d}"[-11:] for index in range(1, 7)]
    urls = [f"https://www.youtube.com/watch?v={video_id}" for video_id in ids]
    gemini = FakeGemini([_factual_payload() for _ in range(5)])
    youtube = FakeYouTube({}, {})
    client = _client(gemini, youtube, _providers(tmp_path, _gemini_family_yaml()))
    results = client.inspect(urls[:5])
    assert [item.source_mode for item in results] == ["AGENTIC_VIDEO"] * 5
    assert gemini.calls == [{"model": "loaded-from-gemini-family", "urls": urls[:5]}]
    assert youtube.videos.calls == []
    with pytest.raises(TooManyYouTubeUrls):
        client.inspect(urls)
    assert len(gemini.calls) == 1


def test_captions_download_is_unsupported(tmp_path: Path) -> None:
    client = _client(
        FakeGemini(_factual_payload()),
        FakeYouTube({}, {}),
        _providers(tmp_path, _gemini_family_yaml()),
    )
    with pytest.raises(UnsupportedCaptionsDownload):
        client.captions.download(id=VIDEO_ID)
    with pytest.raises(UnsupportedCaptionsDownload):
        client.download_captions(WATCH)
    with pytest.raises(UnsupportedCaptionsDownload):
        client.inspect([WATCH], captions=True)


def test_mp4_urls_are_refused_before_any_client_call(tmp_path: Path) -> None:
    gemini = FakeGemini(_factual_payload())
    youtube = FakeYouTube({}, {})
    client = _client(gemini, youtube, _providers(tmp_path, _gemini_family_yaml()))
    with pytest.raises(Mp4DownloadForbidden):
        client.inspect(["https://example.com/clip.mp4"])
    assert gemini.calls == []
    assert youtube.videos.calls == []
    assert gemini.download_mp4_calls == 0
