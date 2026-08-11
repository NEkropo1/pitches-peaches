"""Stage 6 — diagrams, the index, the HTML card, and optionally audio.

Everything here except the diagrams and the narration scripts is deterministic:
the markdown documents already exist, and ``fit.html`` renders the same
``Match`` object as ``02-fit.md`` with no extra model call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .. import tts as tts_module
from ..cards import html_card, mermaid_block
from ..llm import LLM
from ..models import Diagrams, Match, Playbook
from ..prompts import render as render_prompt
from ..state import RunState
from ..tts.normalize import estimate_duration

Reporter = Callable[[str], None]

DOCUMENTS = [
    ("01-company.md", "The company, the product, and the people"),
    ("02-fit.md", "How this role fits what you have already done"),
    ("03-playbook.md", "What they will ask, and answers at depth"),
]


def run(
    state: RunState,
    llm: LLM,
    *,
    audio: bool | None = None,
    report: Reporter = lambda _: None,
) -> None:
    state.require("recon.json", "match.json")
    recon = state.read_json("recon.json")
    match = Match.model_validate(state.read_json("match.json"))

    playbook: Playbook | None = None
    if state.has("playbook.json"):
        playbook = Playbook.model_validate(state.read_json("playbook.json"))

    _write_html(state, recon, match, report)
    _write_diagrams(state, llm, recon, playbook, report)
    _write_index(state, recon, match, report)

    want_audio = llm.config.audio if audio is None else audio
    if want_audio:
        _write_audio(state, llm, report)
    else:
        report("audio: off (pass --audio to render narration)")

    state.record("render", audio=bool(want_audio))


# -- pieces ------------------------------------------------------------------


def _write_html(state: RunState, recon: dict, match: Match, report: Reporter) -> None:
    state.write_text(
        "fit.html",
        html_card(
            match, role=recon.get("role_title", ""), company=recon.get("company", "")
        ),
    )
    report("wrote fit.html")


def _write_diagrams(
    state: RunState, llm: LLM, recon: dict, playbook: Playbook | None, report: Reporter
) -> None:
    process = "unknown"
    if playbook and playbook.rounds:
        process = json.dumps(
            [r.model_dump(mode="json") for r in playbook.rounds], indent=2
        )
    elif recon.get("known_process"):
        process = str(recon["known_process"])

    report("drawing diagrams")
    result = llm.parse(
        Diagrams,
        system=render_prompt(
            "mermaid",
            recon=json.dumps(recon, indent=2, ensure_ascii=False),
            process=process,
        ),
        content="Emit the diagrams.",
    )

    diagrams_dir = Path("diagrams")
    written = []
    for diagram in result.diagrams:
        source = diagram.mermaid.strip()
        if source.startswith("```"):  # belt and braces; the prompt asks for no fence
            source = source.strip("`").removeprefix("mermaid").strip()
        state.write_text(str(diagrams_dir / f"{diagram.name}.mermaid"), source)
        written.append((diagram, source))

    if written:
        lines = ["# Diagrams", ""]
        for diagram, source in written:
            lines += [
                f"## {diagram.title}",
                "",
                mermaid_block(source),
                "",
                f"*Also written to `diagrams/{diagram.name}.mermaid`.*",
                "",
            ]
        state.write_text("04-diagrams.md", "\n".join(lines))
        report(f"wrote {len(written)} diagram(s)")


def _write_index(state: RunState, recon: dict, match: Match, report: Reporter) -> None:
    company = recon.get("company", "the company")
    role = recon.get("role_title", "the role")

    lines = [
        f"# {role} at {company}",
        "",
        "Everything here is a local file. PitchesPeaches did not apply to this "
        "job, contact anyone, or send anything anywhere.",
        "",
        f"**Fit: {match.overall}/100 — {match.band}.** "
        + ("Provisional: the probe loop was skipped. " if match.provisional else "")
        + "Open `fit.html` in a browser for the card.",
        "",
        "## Read in this order",
        "",
    ]
    for name, blurb in DOCUMENTS:
        if state.has(name):
            lines.append(f"1. [{name}]({name}) — {blurb}")
    if state.has("04-diagrams.md"):
        lines.append("1. [04-diagrams.md](04-diagrams.md) — the system and the process")
    lines.append("")

    if state.has("scripts"):
        lines += [
            "## Audio",
            "",
            "Narration scripts are in `scripts/`. Any `.wav` next to them was "
            "synthesized locally.",
            "",
        ]

    claims = recon.get("claims", [])
    unverified = [
        c for c in claims if c.get("confidence") in {"inferred", "unverified"}
    ]
    if unverified:
        lines += [
            "## Confirm on the call",
            "",
            "These are not established facts. Do not repeat them as if they were.",
            "",
        ]
        for claim in unverified[:12]:
            lines.append(f"- *{claim['confidence']}* — {claim['statement']}")
        lines.append("")

    lines += [
        "## Files",
        "",
        "| File | What it is |",
        "|---|---|",
        "| `run.json` | Which stages ran, and the decision you made |",
        "| `recon.json` | The company record, every claim labelled |",
        "| `recon-notes.md` | Raw research notes with sources |",
        "| `profile.json` | Your CV, structured, plus anything you added |",
        "| `match.json` | The fit card data |",
        "| `gate.json` | The recommendation and why |",
        "| `playbook.json` | Questions and reference answers |",
        "",
    ]
    state.write_text("00-README.md", "\n".join(lines))
    report("wrote 00-README.md")


def _write_audio(state: RunState, llm: LLM, report: Reporter) -> None:
    scripts_dir = Path("scripts")
    scripts: list[tuple[str, str]] = []

    for name, _ in DOCUMENTS:
        if not state.has(name):
            continue
        stem = name.removesuffix(".md")
        script_path = state.artifact_path(str(scripts_dir / f"{stem}.txt"))
        if script_path.exists():
            report(f"script exists, reusing: scripts/{stem}.txt")
            scripts.append((stem, script_path.read_text(encoding="utf-8")))
            continue

        report(f"writing narration for {name}")
        document = state.artifact_path(name).read_text(encoding="utf-8")
        script = llm.write(
            system=render_prompt("narration", document=document),
            content=f"Write the narration script for {name}.",
        )
        state.write_text(str(scripts_dir / f"{stem}.txt"), script)
        scripts.append((stem, script))

    if not scripts:
        report("no documents to narrate")
        return

    backend = tts_module.select(llm.config.tts_backend)
    if backend is None:
        report("")
        report("Scripts are written, but no TTS backend is available. Install one:")
        report("  " + tts_module.install_hint())
        return

    report(f"synthesizing with {backend.name}")
    for stem, script in scripts:
        out = state.artifact_path(str(scripts_dir / f"{stem}.wav"))
        estimate = estimate_duration(script, llm.config.rate)
        report(f"  {stem} (~{estimate / 60:.0f} min)")
        result = backend.synthesize(
            script, out, llm.config.voice, llm.config.rate
        )
        report(
            f"  wrote {result.path.name} — {result.seconds / 60:.1f} min, "
            f"{result.words:,} words, {result.voice} @ {result.rate}wpm"
        )
