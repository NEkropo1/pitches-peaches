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
from ..tts import install as tts_install
from ..cards import html_card, mermaid_block
from ..llm import LLM
from ..models import Diagrams, Match, Playbook
from ..prompts import render as render_prompt
from ..state import RunState
from ..tts.normalize import estimate_duration

Reporter = Callable[[str], None]
#: ``(question, default) -> bool``. ``None`` means nobody is there to answer.
Confirm = Callable[[str, bool], bool]

DOCUMENTS = [
    ("01-company.md", "The company, the product, and the people"),
    ("02-fit.md", "How this role fits what you have already done"),
    ("03-playbook.md", "What they will ask, and answers at depth"),
]

#: Which documents are worth listening to. The fit card is not one of them.
#:
#: It is a scored table — four dimensions, a number and a bar each, then quotes
#: with their sources. Read aloud that is "technical, ninety. ownership,
#: ninety-three", and the thing that makes it useful on a page, seeing the shape
#: of four scores at once, is exactly what a voice cannot do. `fit.html` exists
#: for that. The other two are prose, which is what you can take on a walk.
#:
#: Narrating it anyway cost a model call and six and a half minutes of audio
#: nobody would play twice.
NARRATED = ("01-company.md", "03-playbook.md")


def run(
    state: RunState,
    llm: LLM,
    *,
    audio: bool | None = None,
    report: Reporter = lambda _: None,
    confirm: Confirm | None = None,
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
        _write_audio(state, llm, report, confirm)
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
            lines.append(f"1. [{name}]({state.link_to(name)}) — {blurb}")
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
        f"| `{state.link_to('recon.json')}` | The company record, every claim labelled |",
        f"| `{state.link_to('recon-notes.md')}` | Raw research notes with sources |",
        "| `profile.json` | Your CV, structured, plus anything you added |",
        "| `match.json` | The fit card data |",
        "| `gate.json` | The recommendation and why |",
        "| `playbook.json` | Questions and reference answers |",
        "",
    ]
    state.write_text("00-README.md", "\n".join(lines))
    report("wrote 00-README.md")


def _write_audio(
    state: RunState, llm: LLM, report: Reporter, confirm: Confirm | None = None
) -> None:
    scripts_dir = Path("scripts")
    scripts: list[tuple[str, str]] = []

    for name in NARRATED:
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

    _synthesize(state, llm.config, scripts, report, confirm)


def _synthesize(
    state: RunState,
    config,
    scripts: list[tuple[str, str]],
    report: Reporter,
    confirm=None,
) -> None:
    """Turn written scripts into audio, or explain why not.

    Its own function so the failure path is reachable from a test: the bug that
    put it here only shows up when a backend blows up part-way through, which
    is precisely what no happy-path test exercises.
    """
    scripts_dir = Path("scripts")
    backend = tts_module.select(config.tts_backend)

    if backend is None or backend.name != "kokoro":
        # Kokoro installed but mute is the common case, not an exotic one: the
        # audio extra cannot express its own pronunciation model as a
        # dependency. Offer the one wheel that fixes it, then look again.
        if tts_module.kokoro_is_only_missing_its_model() and (
            tts_install.ensure_pronunciation_model(confirm=confirm, report=report)
        ):
            backend = tts_module.select(config.tts_backend)

    if backend is None:
        report("")
        report("Scripts are written, but no TTS backend is available. Install one:")
        report("  " + tts_module.install_hint())
        return

    report(f"synthesizing with {backend.name}")
    for stem, script in scripts:
        out = state.artifact_path(str(scripts_dir / f"{stem}.wav"))
        estimate = estimate_duration(script, config.rate)
        report(f"  {stem} (~{estimate / 60:.0f} min)")
        try:
            result = backend.synthesize(
                script, out, config.voice, config.rate
            )
        except BaseException as exc:  # noqa: BLE001 — see below
            # BaseException, not Exception, and this is the whole point.
            #
            # Kokoro's grapheme-to-phoneme layer downloads a spaCy model on
            # first use, and spaCy's downloader calls sys.exit() when the
            # install command fails — which it does inside a uv-created venv,
            # because there is no pip module there and spaCy prefers
            # `sys.executable -m pip` whenever *any* pip is on PATH. The
            # SystemExit that comes back is not an Exception, so it sails
            # through every handler in this project and takes the process with
            # it.
            #
            # Audio is the last and most optional thing a run does. Everything
            # expensive is already on disk by now, so a voice that will not
            # synthesize is a note, never the end of the run.
            if isinstance(exc, KeyboardInterrupt):
                raise
            report(f"  could not synthesize {stem}: {_why(exc)}")
            report(f"  the script is still at scripts/{stem}.txt")
            continue
        report(
            f"  wrote {result.path.name} — {result.seconds / 60:.1f} min, "
            f"{result.words:,} words, {result.voice} @ {result.rate}wpm"
        )


def _why(exc: BaseException) -> str:
    """A one-line reason, since a SystemExit carries a status and no message."""
    if isinstance(exc, SystemExit):
        return (
            "the backend exited while preparing itself. This is usually kokoro "
            "downloading its spaCy model with a pip that the environment does "
            "not have — see `peaches version` for the fix"
        )
    return str(exc) or exc.__class__.__name__
