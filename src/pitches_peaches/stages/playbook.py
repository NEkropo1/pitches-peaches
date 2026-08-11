"""Stage 5 — the technical playbook.

Two branches, chosen by ``recon.org_type``. Large orgs have legible, repeatable
processes worth predicting; small ones have a person worth understanding.

Both branches end in the same technical core: a few technologies, a few
non-obvious questions each, and reference answers at architectural-interview
depth. The tool does not grade the reader's answers — it supplies questions and
answers, and they decide what they know.
"""

from __future__ import annotations

import json
from typing import Callable

from ..llm import LLM
from ..models import Match, Playbook
from ..prompts import render
from ..state import RunState

Reporter = Callable[[str], None]

STRUCTURED_ORGS = {"enterprise", "scaleup", "agency"}


def branch_for(org_type: str) -> str:
    return "structured" if org_type in STRUCTURED_ORGS else "founder_led"


def run(
    state: RunState,
    llm: LLM,
    *,
    force: bool = False,
    report: Reporter = lambda _: None,
) -> Playbook:
    state.require("recon.json", "profile.json", "match.json")
    state.require_gate_passed(force=force)

    recon = state.read_json("recon.json")
    profile = state.read_json("profile.json")
    match = state.read_json("match.json")

    branch = branch_for(recon.get("org_type", "unknown"))
    report(f"branch: {branch.replace('_', '-')}")

    system = render(
        "playbook",
        branch=branch,
        branch_instructions=render(f"playbook_{branch}"),
        max_technologies=llm.config.max_technologies,
        max_questions_per_tech=llm.config.max_questions_per_tech,
        seniority=recon.get("seniority", "unknown"),
        recon=json.dumps(recon, indent=2, ensure_ascii=False),
        profile=json.dumps(profile, indent=2, ensure_ascii=False),
        match=json.dumps(match, indent=2, ensure_ascii=False),
    )

    report("writing the playbook (this is the long one)")
    playbook = llm.parse(
        Playbook,
        system=system,
        content=(
            "Emit the playbook. The answers are the product — go to mechanism "
            "depth and do not summarise."
        ),
        effort=llm.config.effort,
        max_tokens=64_000,
    )

    # The caps are ours to enforce, not the model's to remember.
    playbook.technologies = playbook.technologies[: llm.config.max_technologies]
    for tech in playbook.technologies:
        tech.questions = tech.questions[: llm.config.max_questions_per_tech]

    state.write_json("playbook.json", playbook)
    state.write_text("03-playbook.md", markdown(playbook, recon, Match.model_validate(match)))

    state.record(
        "playbook",
        branch=branch,
        technologies=[t.technology for t in playbook.technologies],
        questions=sum(len(t.questions) for t in playbook.technologies),
    )
    return playbook


def markdown(playbook: Playbook, recon: dict, match: Match) -> str:
    """Render the playbook. Deterministic — the prose is already in the record."""
    role = recon.get("role_title", "the role")
    company = recon.get("company", "")
    lines = [f"# Playbook: {role} at {company}".rstrip(), ""]

    lines += [
        "This supplies questions and reference answers. It does not grade you, "
        "score your answers, or run a mock interview. Read it, decide what you "
        "know, and close the gaps you care about.",
        "",
    ]

    if playbook.rounds:
        lines += ["## The process", ""]
        for rnd in playbook.rounds:
            head = rnd.name + (f" — {rnd.duration}" if rnd.duration else "")
            lines += [
                f"### {head}",
                "",
                f"**What is actually being assessed.** {rnd.what_is_assessed}",
                "",
                rnd.how_to_run_it,
                "",
            ]

    if playbook.interviewer_profiles:
        lines += ["## Who you are talking to", ""]
        for person in playbook.interviewer_profiles:
            head = person.name + (f" — {person.role}" if person.role else "")
            lines += [f"### {head}", ""]
            if person.background:
                lines += [person.background, ""]
            if person.what_they_will_probe:
                lines += [f"**Likely to probe.** {person.what_they_will_probe}", ""]
            if person.sources:
                lines += ["Sources: " + ", ".join(person.sources), ""]

    if playbook.pitch_adaptation:
        lines += ["## Adapting your pitch", "", playbook.pitch_adaptation, ""]

    lines += ["## The technical core", ""]
    for tech in playbook.technologies:
        lines += [f"### {tech.technology}", "", tech.why_it_matters_here, ""]
        for index, question in enumerate(tech.questions, 1):
            lines += [
                f"#### {index}. {question.question}",
                "",
                f"*Why this one, and not the obvious one:* {question.why_this_one}",
                "",
                question.answer,
                "",
            ]
            for dive in question.deep_dives:
                lines += [f"##### Deep dive — {dive.topic}", "", dive.walkthrough, ""]

    if playbook.closing_questions:
        lines += ["## What you ask them", ""]
        lines += [f"- {q}" for q in playbook.closing_questions]
        lines.append("")

    if match.prepare:
        lines += ["## From the fit card — what to rehearse", ""]
        lines += [f"- {item}" for item in match.prepare]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
