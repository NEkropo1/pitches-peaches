"""Stage 3 — score this role against this person, from their side.

The scores come from the model. There is no weighting table in Python, because
calibrating one honestly needs ground-truth match data this project does not
have, and a hand-picked weight table is fake precision. What makes the number
worth reading is the structure around it: four fixed dimensions, and every
positive point carrying the actual line from the CV it came from.

The one deterministic check is on our own output — a quote that is not really
in the source gets dropped before the reader sees it.

**Ask first, then score once.** Working out what is missing from a CV needs the
posting and the CV; it does not need a finished card. So the questions come
from their own small call, the reader answers them, and the card is generated
one time with the answers already in hand. The earlier shape scored in full,
showed a draft, collected answers and then scored in full again — paying for
the longest generation in the stage twice and discarding the first result. It
also anchored the reader on a number that was about to change.
"""

from __future__ import annotations

import json
from typing import Callable

from ..llm import LLM
from ..models import Match, MatchDraft, Probe, ProbeSet, Profile, band_for
from ..prompts import render
from ..quotes import filter_fit_points
from ..state import RunState

Reporter = Callable[[str], None]
Asker = Callable[[str], str]

#: The prompt asks for at most this many. The cap is ours to enforce.
MAX_PROBES = 8


def _ask_what(llm: LLM, recon: dict, profile: dict) -> list[Probe]:
    """Decide what to ask, before anything is scored.

    Runs at ``parse_effort`` rather than ``effort``: this is extraction shaped
    — read two documents, name what is missing from one of them — and its
    output is a few dozen words per question, not a card.
    """
    result = llm.parse(
        ProbeSet,
        system=render(
            "probes",
            recon=json.dumps(recon, indent=2, ensure_ascii=False),
            profile=json.dumps(profile, indent=2, ensure_ascii=False),
        ),
        content=(
            "Emit the questions worth putting to this person before their fit "
            "is scored. Ask nothing the two documents already answer."
        ),
        effort=llm.config.parse_effort,
    )
    return result.probes[:MAX_PROBES]


def _score(llm: LLM, recon: dict, profile: dict, *, probes_collected: bool) -> MatchDraft:
    branch = "collected" if probes_collected else "wanted"
    return llm.parse(
        MatchDraft,
        system=render(
            "match",
            probes_note=render(f"match_probes_{branch}"),
            recon=json.dumps(recon, indent=2, ensure_ascii=False),
            profile=json.dumps(profile, indent=2, ensure_ascii=False),
        ),
        content=(
            "Score this role against this person and emit the match record. "
            "Every quote must be copied verbatim from their CV or their answers."
        ),
        effort=llm.config.effort,
    )


def _finish(
    draft: MatchDraft,
    source: str,
    *,
    probes: list[Probe],
    provisional: bool,
) -> tuple[Match, list[str]]:
    """Apply quote verification and derive the band. Returns (match, warnings)."""
    check = filter_fit_points(draft.fit_points, source)
    match = Match(
        overall=draft.overall,
        band=band_for(draft.overall),
        dimensions=draft.dimensions,
        fit_points=check.kept,
        gaps=draft.gaps,
        prepare=draft.prepare,
        probes=probes,
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

    answered = 0
    probes: list[Probe] = []
    if interactive and ask is not None:
        report("working out what to ask you")
        probes = _ask_what(llm, recon, profile.model_dump(mode="json"))

    if probes:
        report("")
        report("A few questions before this gets scored, so the card is written")
        report("with your answers already in it. Anything you add counts the same")
        report("as your CV, and there is no wrong answer — nothing is being tested.")
        report("Press enter to skip one, or type 'stop' to finish early.")
        report("")

        for probe in probes:
            report(f"  why: {probe.why}")
            answer = ask(probe.question).strip()
            if answer.lower() in {"stop", "quit", "q"}:
                break
            if not answer:
                continue
            answered += 1
            profile.extra_notes.append(f"Q: {probe.question}\nA: {answer}")
            source += f"\n{answer}"
        report("")

        # Before the scoring call, not after: they just typed these by hand,
        # and a provider error must not be what loses them.
        state.write_json("profile.json", profile)

    report(f"scoring with {answered} answer(s)" if answered else "scoring")
    draft = _score(
        llm,
        recon,
        profile.model_dump(mode="json"),
        probes_collected=bool(probes),
    )
    match, warnings = _finish(
        draft,
        source,
        probes=probes or draft.probes,
        provisional=not interactive,
    )
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
        probes_asked=len(probes),
        probes_answered=answered,
        quotes_dropped=len(warnings),
    )
    return match
