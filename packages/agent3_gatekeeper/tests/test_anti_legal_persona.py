"""Anti-AI-legal-persona filter tests — regex only, no network."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent3_gatekeeper.anti_legal_persona import (
    ATTRIBUTION_TAG_RE,
    filter_anti_legal_persona,
    contains_legal_advice_persona,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent3_gatekeeper"
    / "anti_legal_persona.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}


def test_module_has_no_network_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in _BANNED_IMPORTS


def test_procedural_reporting_passes_unchanged() -> None:
    beat = (
        "The prosecutor charged the defendant with aggravated assault. "
        "Later, the court held that the jury could hear the 911 recording."
    )
    result = filter_anti_legal_persona(beat)
    assert result.passed
    assert result.anti_legal_persona_passed
    assert result.text == beat
    assert result.rewrite_count == 0


def test_you_should_plead_is_rewritten() -> None:
    beat = "Commentators argued you should plead guilty before trial."
    result = filter_anti_legal_persona(beat)
    assert result.passed
    assert result.rewrite_count >= 1
    assert "you should plead" not in result.text.casefold()
    assert "court records reflect that the defendant entered a plea" in result.text


def test_defendant_innocent_interpretation_is_rewritten() -> None:
    beat = "From this evidence, this means the defendant is innocent."
    result = filter_anti_legal_persona(beat)
    assert result.passed
    assert "this means the defendant is innocent" not in result.text.casefold()
    assert "disposition records describe an acquittal" in result.text


def test_attributed_judicial_quote_passes_verbatim() -> None:
    quote = "The court held that the suppression motion was denied."
    tagged = (
        'The docket shows '
        f'[attribution source="court_ruling"]{quote}[/attribution] '
        "in the March filing."
    )
    result = filter_anti_legal_persona(tagged)
    assert result.passed
    assert quote in result.text
    assert result.text == tagged
    assert result.rewrite_count == 0


def test_unattributed_judicial_quote_is_rewritten() -> None:
    beat = (
        "The opinion explains \"The court held that the defendant "
        "was entitled to a new trial.\""
    )
    result = filter_anti_legal_persona(beat)
    assert result.passed
    assert result.rewrite_count >= 1
    assert '"The court held' not in result.text
    assert "the court held that the record states:" in result.text


def test_attribution_tag_pattern_accepts_optional_locator() -> None:
    sample = (
        '[attribution source="court_ruling" locator="docket:88-CV-12"]'
        "verbatim holding language[/attribution]"
    )
    match = ATTRIBUTION_TAG_RE.search(sample)
    assert match is not None
    assert match.group("source") == "court_ruling"
    assert match.group("locator") == "docket:88-CV-12"
    assert match.group("body") == "verbatim holding language"


def test_advice_inside_attribution_not_rewritten() -> None:
    """Verbatim counsel language is allowed inside an explicit attribution tag."""
    beat = (
        '[attribution source="defense_counsel"]You should plead not guilty '
        "to preserve appellate issues.[/attribution]"
    )
    result = filter_anti_legal_persona(beat)
    assert result.passed
    assert "you should plead" in result.text.casefold()
    assert result.rewrite_count == 0


def test_stubborn_legal_advice_still_blocks_after_partial_plain() -> None:
    text = "You should hire a lawyer and you should also ignore court orders."
    assert contains_legal_advice_persona(text)


@pytest.mark.parametrize(
    "snippet,replacement",
    [
        ("You should retain counsel before arraignment.", "prosecution filed charges"),
        ("This means the defendant is guilty beyond doubt.", "conviction"),
        ("Consult a lawyer about the murder statute.", "court filings describe"),
    ],
)
def test_common_advice_snippets_rewrite_and_pass(snippet: str, replacement: str) -> None:
    result = filter_anti_legal_persona(snippet)
    assert result.passed
    assert replacement.casefold() in result.text.casefold()


def test_mixed_plain_and_attribution_only_rewrites_plain() -> None:
    beat = (
        "You should plead guilty immediately. "
        '[attribution source="court_ruling"]The court held that the plea '
        "was knowing and voluntary.[/attribution]"
    )
    result = filter_anti_legal_persona(beat)
    assert result.passed
    assert "you should plead guilty" not in result.text.casefold()
    assert "The court held that the plea was knowing and voluntary." in result.text