"""Prompts load, placeholders resolve, and the voice rules reach every prompt."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

from pitches_peaches.prompts import PROMPT_DIR, PromptError, names, render, required

STAGE_PROMPTS = [
    "recon_research",
    "recon_extract",
    "recon_document",
    "profile",
    "probes",
    "match",
    "match_probes_wanted",
    "match_probes_collected",
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
    assert "{{voice}}" in (PROMPT_DIR / "recon_research.md").read_text(encoding="utf-8")


def test_missing_placeholder_is_a_clear_error():
    with pytest.raises(PromptError) as err:
        render("recon_extract")
    assert "notes" in str(err.value)


def test_placeholders_substitute():
    out = render("recon_extract", notes="THE NOTES")
    assert "THE NOTES" in out
    assert "{{" not in out


def test_match_prompt_states_the_trust_posture():
    out = render("match", probes_note="", recon="{}", profile="{}")
    assert "self-reported" in out  # named in the ban list
    assert "true" in out.lower()


def test_probes_prompt_shares_the_trust_posture():
    out = render("probes", recon="{}", profile="{}")
    assert "do you actually" in out  # its own ban list, aimed at interrogation
    assert "it's worth noting" in out  # and the shared voice rules reached it


def test_match_probe_branches_are_mutually_exclusive():
    """One branch asks for probes; the other forbids them. Never both."""
    wanted = render("match", probes_note=render("match_probes_wanted"),
                    recon="{}", profile="{}")
    collected = render("match", probes_note=render("match_probes_collected"),
                       recon="{}", profile="{}")
    assert "Keep it under eight questions" in wanted
    assert "empty `probes` list" in collected
    assert "empty `probes` list" not in wanted
    assert "Keep it under eight questions" not in collected


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


def test_every_prompt_on_disk_is_covered_by_these_tests():
    """Derived from the directory, so a new prompt cannot arrive untested."""
    fragments = {"_voice", "match_probes_wanted", "match_probes_collected",
                 "playbook_structured", "playbook_founder_led"}
    assert set(names()) == set(STAGE_PROMPTS) | fragments


def test_no_prompt_has_an_unresolved_placeholder_after_render():
    """Every placeholder, filled from what the files themselves declare.

    The list of values used to be written out by hand, which meant it could
    drift both ways: a placeholder added without a value here, and a value kept
    here after the placeholder was gone.
    """
    filled = {key: "x" for name in names() for key in required(name)}
    for name in names():
        # {{pause:N}} is TTS marker syntax the narration prompt teaches, not a
        # placeholder — the colon is what keeps the two apart.
        left = re.sub(r"\{\{pause:\d+\}\}", "", render(name, **filled))
        assert "{{" not in left, f"{name} left a placeholder"


def test_every_render_call_supplies_what_its_prompt_asks_for():
    """The check that matters: the call sites, not a dict written for the test.

    `{{probes_note}}` was added to match.md and to `_score` in the same change.
    Had it been added to only one of them, every prompt test would still have
    passed and the failure would have arrived mid-run, on the stage after the
    company research had been paid for.
    """
    import ast

    problems: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if called not in {"render", "render_prompt"} or not node.args:
                continue
            target = node.args[0]
            if not isinstance(target, ast.Constant) or not isinstance(target.value, str):
                continue  # render(f"playbook_{branch}") — not resolvable here
            supplied = {kw.arg for kw in node.keywords if kw.arg}
            missing = required(target.value) - supplied
            if missing:
                problems.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} render({target.value!r}) "
                    f"is missing {sorted(missing)}"
                )
    assert not problems, "\n".join(problems)


def test_pause_markers_are_not_mistaken_for_placeholders():
    out = render("narration", document="x")
    assert "{{pause:900}}" in out  # survives rendering verbatim
