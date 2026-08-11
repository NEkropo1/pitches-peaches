"""Stage 3 — score this role against this person, from their side.

The scores come from the model. There is no weighting table in Python, because
calibrating one honestly needs ground-truth match data this project does not
have, and a hand-picked weight table is fake precision. What makes the number
worth reading is the structure around it: four fixed dimensions, and every
positive point carrying the actual line from the CV it came from.

The one deterministic check is on our own output — a quote that is not really
in the source gets dropped before the reader sees it.
"""

from __future__ import annotations

import json
from typing import Callable

from ..cards import terminal_lines
from ..llm import LLM
from ..models import Match, MatchDraft, Profile, band_for
from ..prompts import render
from ..quotes import filter_fit_points
from ..state import RunState

Reporter = Callable[[str], None]
Asker = Callable[[str], str]


def _score(llm: LLM, recon: dict, profile: dict) -> MatchDraft:
    return llm.parse(
        MatchDraft,
        system=render(
            "match",
            recon=json.dumps(recon, indent=2, ensure_ascii=False),
            profile=json.dumps(profile, indent=2, ensure_ascii=False),
        ),
        content=(
            "Score this role against this person and emit the match record. "
            "Every quote must be copied verbatim from their CV or their answers."
        ),
        effort=llm.config.effort,
    )


def _finish(draft: MatchDraft, source: str, provisional: bool) -> tuple[Match, list[str]]:
    """Apply quote verification and derive the band. Returns (match, warnings)."""
    check = filter_fit_points(draft.fit_points, source)
    match = Match(
        overall=draft.overall,
        band=band_for(draft.overall),
        dimensions=draft.dimensions,
        fit_points=check.kept,
        gaps=draft.gaps,
        prepare=draft.prepare,
        probes=draft.probes,
        provisional=provisional,
    )
    return match, check.warnings


def run(
    state: RunState,
    llm: LLM,
    *,
    interactive: bool = True,
    notes_path: str | None = None,
    report: Reporter = lambda _: None,
    ask: Asker | None = None,
) -> Match:
    state.require("recon.json", "profile.json")
    recon = state.read_json("recon.json")
    profile_data = state.read_json("profile.json")
    profile = Profile.model_validate(profile_data)

    source = ""
    if state.has("cv-source.txt"):
        source = state.artifact_path("cv-source.txt").read_text(encoding="utf-8")
    source = "\n".join(
        [source, json.dumps(profile_data, ensure_ascii=False), *profile.extra_notes]
    )

    if notes_path:
        from pathlib import Path

        extra = Path(notes_path).expanduser().read_text(encoding="utf-8").strip()
        if extra:
            profile.extra_notes.append(extra)
            source += "\n" + extra
            report("added your notes to the profile")

    report("scoring")
    draft = _score(llm, recon, profile.model_dump(mode="json"))
    match, warnings = _finish(draft, source, provisional=not interactive)
    for warning in warnings:
        report(f"  note: {warning}")

    answered = 0
    if interactive and match.probes and ask is not None:
        report("")
        for line in terminal_lines(
            match, role=recon.get("role_title", ""), company=recon.get("company", "")
        ):
            report(line)
        report("")
        report("A few questions. Anything you add counts the same as your CV.")
        report("Press enter to skip one, or type 'stop' to finish early.")
        report("")

        for probe in match.probes:
            answer = ask(probe.question).strip()
            if answer.lower() in {"stop", "quit", "q"}:
                break
            if not answer:
                continue
            answered += 1
            profile.extra_notes.append(f"Q: {probe.question}\nA: {answer}")
            source += f"\n{answer}"

        if answered:
            report("")
            report(f"re-scoring with {answered} answer(s)")
            state.write_json("profile.json", profile)
            draft = _score(llm, recon, profile.model_dump(mode="json"))
            match, warnings = _finish(draft, source, provisional=False)
            for warning in warnings:
                report(f"  note: {warning}")

    state.write_json("profile.json", profile)
    state.write_json("match.json", match)

    from ..cards import markdown

    state.write_text(
        "02-fit.md",
        markdown(
            match,
            role=recon.get("role_title", ""),
            company=recon.get("company", ""),
        ),
    )

    state.record(
        "match",
        overall=match.overall,
        band=match.band,
        provisional=match.provisional,
        probes_answered=answered,
        quotes_dropped=len(warnings),
    )
    return match
