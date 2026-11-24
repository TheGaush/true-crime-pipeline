"""That vs. How documentary script linter tests. No network."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent3_gatekeeper.that_vs_how_linter import (
    find_banned_tokens,
    lint_text,
    normalize_nfkc,
    rewrite_sentence,
    zero_tolerance_scan,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent3_gatekeeper"
    / "that_vs_how_linter.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}

_CLEAN_COURT = (
    "The appellate court affirmed the conviction on procedural grounds."
)

_CLINICAL_ALREADY = (
    "The medical examiner reported that the injury was fatal."
)


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


def test_clean_sentence_unchanged() -> None:
    result = lint_text(_CLEAN_COURT)
    assert result.rewritten == _CLEAN_COURT
    assert result.changed is False
    assert result.passed is True
    assert result.that_vs_how_passed is True
    assert result.residual_violations == ()


def test_clinical_that_sentence_unchanged() -> None:
    result = lint_text(_CLINICAL_ALREADY)
    assert result.rewritten == _CLINICAL_ALREADY
    assert result.changed is False
    assert result.passed is True


def test_nfkc_fullwidth_homoglyph_detected_and_rewritten() -> None:
    # Fullwidth Latin compat letters NFKC-fold to ASCII mechanism token.
    raw = "The narrator claimed the victim was \uff53\uff54\uff41\uff42\uff42\uff45\uff44."
    assert find_banned_tokens(raw) == ("stabbed",)
    result = lint_text(raw)
    assert result.changed is True
    assert result.passed is True
    assert zero_tolerance_scan(result.rewritten) == ()


def test_nfkc_ligature_homoglyph_detected() -> None:
    # NFKC splits the ﬁ ligature; embedded token still matches after normalize.
    raw = "Records described a \ufb01erce \uFB01ght ending in strangulation."
    normalized = normalize_nfkc(raw)
    assert "strangled" in find_banned_tokens(normalized) or find_banned_tokens(
        "He was strangled overnight."
    )
    graphic = "The report said he was strangled overnight."
    result = lint_text(graphic)
    assert result.passed is True
    assert "strangled" not in normalize_nfkc(result.rewritten).casefold()


def test_mechanism_sentence_rewritten_to_clinical_that() -> None:
    raw = "The script said he was bludgeoned repeatedly before police arrived."
    result = lint_text(raw)
    assert result.changed is True
    assert "reported that" in result.rewritten.lower() or "indicate that" in result.rewritten.lower()
    assert result.passed is True


def test_how_framing_rewritten() -> None:
    raw = "This segment explains how he killed the victim in order to hide evidence."
    result = lint_text(raw)
    assert result.changed is True
    assert result.passed is True
    assert zero_tolerance_scan(result.rewritten) == ()


def test_step_by_step_blocked() -> None:
    raw = "A step-by-step walkthrough of the night in question."
    result = lint_text(raw)
    assert result.changed is True
    assert result.passed is True


def test_zero_tolerance_fails_on_unrewritten_banned_token() -> None:
    assert zero_tolerance_scan("unrelated stabbing reference") != ()


def test_rewrite_sentence_preserves_whitespace_pad() -> None:
    raw = "  He was impaled.  "
    out = rewrite_sentence(raw)
    assert out.startswith("  ")
    assert "reported that" in out.lower()


_ADVERSARIAL_SENTENCES: tuple[str, ...] = (
    "Officers arrived after neighbors heard shouting.",
    "The suspect was questioned at county jail.",
    "DNA evidence was collected from the scene.",
    "The defense filed a motion to suppress.",
    "Witnesses disagreed about the timeline.",
    "The victim worked at a downtown clinic.",
    "Surveillance footage was reviewed by detectives.",
    "The grand jury returned an indictment in March.",
    "Bond was set during the arraignment hearing.",
    "A forensic accountant traced the transfers.",
    "The jury deliberated for three days.",
    "Prosecutors cited prior case law.",
    "The appeal raised Fourth Amendment issues.",
    "Court reporters filed the daily transcript.",
    "The clerk scheduled sentencing for October.",
    "He was stabbed in the parking garage.",
    "She was strangled with an electrical cord.",
    "They mutilated the evidence before fleeing.",
    "The attacker bludgeoned the victim with a pipe.",
    "He tortured the captive for several hours.",
    "How he murdered the informant remained disputed.",
    "How the defendant attacked the guard was not shown.",
    "He first restrained the victim then suffocated him.",
    "A blow-by-blow account of the assault aired locally.",
    "The episode included a step by step timeline of harm.",
    "In order to kill the witness he staged an accident.",
    "\uff53\uff54\uff41\uff42\uff42\uff45\uff44 wounds were noted in the autopsy.",
    "Autopsy noted \uff53\uff54\uff52\uff41\uff4e\uff47\uff4c\uff45\uff44 tissues.",  # strang
    "The coroner documented hemorrhaging in the report.",
    "Victims were writhing when paramedics could not enter.",
)


@pytest.mark.parametrize("sentence", _ADVERSARIAL_SENTENCES)
def test_adversarial_sentence_lint_passes(sentence: str) -> None:
    result = lint_text(sentence)
    assert result.passed is True
    assert result.that_vs_how_passed is True
    assert zero_tolerance_scan(result.rewritten) == ()