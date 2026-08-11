"""Prompts load, placeholders resolve, and the voice rules reach every prompt."""

import re

import pytest

from pitches_peaches.prompts import PROMPT_DIR, PromptError, render

STAGE_PROMPTS = [
    "recon_research",
    "recon_extract",
    "recon_document",
    "profile",
    "match",
    "gate",
    "playbook",
    "playbook_structured",
    "playbook_founder_led",
    "mermaid",
    "narration",
]


def test_every_prompt_file_is_present():
    on_disk = {p.stem for p in PROMPT_DIR.glob("*.md")}
    assert set(STAGE_PROMPTS) <= on_disk


def test_voice_is_shared_not_duplicated():
    voice = render("recon_research")
    assert "it's worth noting" in voice  # the ban list reached the prompt
    # ...and it is not pasted into the file itself
    assert "{{voice}}" in (PROMPT_DIR / "recon_research.md").read_text()


def test_missing_placeholder_is_a_clear_error():
    with pytest.raises(PromptError) as err:
        render("recon_extract")
    assert "notes" in str(err.value)


def test_placeholders_substitute():
    out = render("recon_extract", notes="THE NOTES")
    assert "THE NOTES" in out
    assert "{{" not in out


def test_match_prompt_states_the_trust_posture():
    out = render("match", recon="{}", profile="{}")
    assert "self-reported" in out  # named in the ban list
    assert "true" in out.lower()


def test_playbook_forbids_the_textbook_questions_by_name():
    out = render(
        "playbook",
        branch="founder_led",
        branch_instructions=render("playbook_founder_led"),
        max_technologies=3,
        max_questions_per_tech=3,
        seniority="senior",
        recon="{}",
        profile="{}",
        match="{}",
    )
    assert "decorator" in out
    assert "CAP theorem" in out
    assert "third-most-likely" in out


def test_no_prompt_has_an_unresolved_placeholder_after_render():
    filled = {
        "notes": "x", "today": "2026-08-11", "recon": "{}", "posting": "x",
        "cv": "x", "profile": "{}", "match": "{}", "document": "x",
        "process": "x", "branch": "structured", "branch_instructions": "x",
        "max_technologies": 3, "max_questions_per_tech": 3, "seniority": "senior",
    }
    for name in STAGE_PROMPTS:
        # {{pause:N}} is TTS marker syntax the narration prompt teaches, not a
        # placeholder — the colon is what keeps the two apart.
        left = re.sub(r"\{\{pause:\d+\}\}", "", render(name, **filled))
        assert "{{" not in left, f"{name} left a placeholder"


def test_pause_markers_are_not_mistaken_for_placeholders():
    out = render("narration", document="x")
    assert "{{pause:900}}" in out  # survives rendering verbatim
