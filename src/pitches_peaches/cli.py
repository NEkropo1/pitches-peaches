"""The `peaches` command.

Six stages, each independently runnable and resumable, plus `init` to scaffold
and `run` to do the lot in order.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from . import (
    VERIFIED_MODEL,
    VERIFIED_PROVIDER,
    __version__,
    is_verified,
    verification_notice,
)
from .config import (
    CONFIG_FILE,
    CONFIG_TEMPLATE,
    GITIGNORE_TEMPLATE,
    Config,
    any_key_present,
    load_dotenv,
)
from . import providers
from .llm import LLM, LLMError
from .prompts import PromptError
from .state import RunState, StageError

app = typer.Typer(
    name="peaches",
    help=(
        "Turn a job posting and your CV into an interview prep dossier. "
        "It never applies to anything."
    ),
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)

CV_EXAMPLE = {
    "_comment": "All values can be overwritten, this is an example. Delete what does not apply.",
    "firstname": "Paul",
    "lastname": "Savchuk",
    "position": "Senior Software Engineer | Python | Rust | AWS | GCP",
    "experience": "13+ years in software development, backend, architecture and automation, 8+ of them commercial",
    "english": "Advanced/Expert (C1)",
    "_comment_english": "Any of: Pre-Intermediate (A2), Intermediate (B1), Upper-Intermediate (B2), Advanced/Expert (C1), Proficient/Master (C2)",
    "location": "Ukraine, Kyiv",
    "linkedIn": "https://www.linkedin.com/in/your-handle",
    "tech_summary": {
        "_comment": "Keys here are dynamic and can be DELETED or EXTENDED.",
        "Programming languages": "Python, Rust, JavaScript, TypeScript, Bash, SQL",
        "Backend technologies": "FastAPI, Flask, Django, SQLAlchemy, Celery, Redis",
        "Cloud platforms": "AWS (Lambda, S3, EC2, SQS), GCP (BigQuery, Pub/Sub, Kubernetes)",
        "Databases": "PostgreSQL, Redis, ClickHouse, MongoDB, BigQuery",
        "Devops": "Docker, Kubernetes, Nginx, GitHub Actions, ArgoCD, CI/CD",
        "Other": "System design, high-load architecture, observability, async, realtime systems",
    },
    "education": {"place": "Kyiv-Mohyla Academy", "degree": "No formal degree"},
    "projects": [
        {
            "_comment": "One entry per distinct piece of work. Country is optional.",
            "name": "High-Frequency Arbitrage Bot on Solana",
            "position": "Lead Rust/Python Developer",
            "duration": "Ongoing (2024–Present)",
            "team_size": "1-2 core contributors",
            "country": "Ukraine",
            "description": "Architected a low-latency trading system integrating several DEXes. Snapshot engine in Python, swaps executed by Rust clients.",
            "stack": "Rust, Python, Solana, Redis, WebSocket, Parquet",
            "responsibilities": [
                "Designed snapshot architecture and pool enrichment pipelines",
                "Implemented pool monitoring and swap routing logic",
                "Built the backtest framework and multi-chain strategy design",
            ],
        }
    ],
}


# -- shared plumbing ---------------------------------------------------------


def _cfg(workdir: Path, **overrides) -> Config:
    load_dotenv(workdir)
    return Config.load(workdir, **overrides)


def _llm(workdir: Path, *, needs: tuple[str, ...] = (), **overrides) -> LLM:
    """The composition root: resolve everything once, then hand it down.

    Order matters for the error the user actually sees. A missing upstream
    artifact is both more likely and more actionable than a credential
    problem, so it is checked first; then provider resolution, which reports
    a missing key, a wrong-provider key, or a missing SDK with the exact fix.
    """
    config = _cfg(workdir, **overrides)
    if needs:
        RunState.load(workdir).require(*needs)

    resolution = providers.resolve(
        config.provider, model=config.model, workdir=workdir
    )
    if config.provider.strip().lower() in ("", "auto"):
        console.print(f"[dim]using {resolution.describe()} — {resolution.reason}[/dim]")
    _warn_if_unverified(resolution)
    return LLM.from_resolution(config, resolution)


def _warn_if_unverified(resolution: "providers.Resolution") -> None:
    """Say so, once, when the run is on a combination nobody has proven.

    Not a nag and not a blocker — the code may well work. It just has not been
    watched working, and a person about to spend money on a dossier they will
    walk into an interview with deserves to know which of those it is.
    """
    if is_verified(resolution.name, resolution.model):
        return
    console.print(
        f"[yellow]note:[/yellow] [dim]v{__version__} has only been run end to end on "
        f"{VERIFIED_PROVIDER}/{VERIFIED_MODEL}. "
        f"{resolution.describe()} is unproven — see DEBRIEF.md.[/dim]"
    )


def _report(message: str) -> None:
    console.print(message, highlight=False)


def _step(message: str) -> None:
    console.print(f"[dim]·[/dim] {message}", highlight=False)


def _ask(question: str) -> str:
    console.print(f"\n[bold]{question}[/bold]", highlight=False)
    try:
        return input("> ")
    except (EOFError, KeyboardInterrupt):
        return "stop"


def _confirm(question: str) -> bool:
    try:
        return typer.confirm(question, default=True)
    except (EOFError, KeyboardInterrupt):
        return False


def _fail(exc: Exception) -> None:
    err.print(f"[red]{exc}[/red]")
    raise typer.Exit(code=1)


def _card(lines: list[str]) -> None:
    for line in lines:
        console.print(line, highlight=False, markup=False)


def _want_audio(flag: Optional[bool], llm: LLM, interactive: bool) -> Optional[bool]:
    """Ask about audio at the end, once the dossier exists.

    Deciding up front means deciding before you know whether the dossier is
    worth listening to — and audio is the slowest, most optional part of the
    run. An explicit --audio/--no-audio still wins, and a non-interactive run
    falls through to the config default rather than blocking on a prompt.
    """
    if flag is not None or not interactive:
        return flag

    from . import tts

    backend = tts.select(llm.config.tts_backend)
    console.print()
    if backend is None:
        console.print(
            "[dim]No TTS backend is installed, so this writes the narration "
            "scripts only — you can synthesize them later.[/dim]"
        )
    else:
        console.print(
            f"[dim]Narration is written for the ear and synthesized with "
            f"{backend.name}. It costs one more model call per document and a "
            f"few minutes.[/dim]"
        )
    try:
        return typer.confirm("Render narration audio?", default=False)
    except (EOFError, KeyboardInterrupt):
        return False


# -- options -----------------------------------------------------------------

WorkdirOpt = typer.Option(
    Path("."), "--workdir", "-C", help="The run directory.", show_default=".",
)
ModelOpt = typer.Option(None, "--model", help="Override the model id.")
ProviderOpt = typer.Option(
    None, "--provider", help="anthropic|openai|gemini|auto"
)
EffortOpt = typer.Option(None, "--effort", help="low|medium|high|xhigh|max")


# -- commands ----------------------------------------------------------------


@app.command()
def init(workdir: Path = WorkdirOpt) -> None:
    """Scaffold a run directory: config, an example CV, and a .gitignore."""
    workdir.mkdir(parents=True, exist_ok=True)
    state = RunState.load_or_create(workdir)

    written = []
    for name, content in (
        (CONFIG_FILE, CONFIG_TEMPLATE),
        (".gitignore", GITIGNORE_TEMPLATE),
        ("cv.example.json", json.dumps(CV_EXAMPLE, indent=2, ensure_ascii=False) + "\n"),
    ):
        path = workdir / name
        if path.exists():
            continue
        path.write_text(content, encoding="utf-8")
        written.append(name)

    console.print(f"[green]ready[/green] in {workdir.resolve()}")
    for name in written:
        console.print(f"  wrote {name}")
    if not written:
        console.print("  (everything was already there)")

    console.print()
    _cfg(workdir)  # loads .env so the check below sees any key already there
    if not any_key_present():
        console.print("Set a provider key, then run recon. Any one of:")
        for provider in providers.all_providers():
            console.print(f"  [bold]export {provider.env_key}=...[/bold]")
    console.print(
        "  [bold]peaches run https://the-job-posting --cv ~/cv.pdf[/bold]"
    )
    state.save()


@app.command()
def recon(
    target: str = typer.Argument(..., help="Job posting URL, or a path to the saved posting."),
    workdir: Path = WorkdirOpt,
    company: Optional[str] = typer.Option(None, "--company", help="Company name, if the posting hides it."),
    posting: Optional[str] = typer.Option(None, "--posting", help="Extra pasted posting text, as a file."),
    model: Optional[str] = ModelOpt,
    effort: Optional[str] = EffortOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Research the company. Writes recon.json and 01-company.md."""
    from .stages import recon as stage

    try:
        state = RunState.load_or_create(workdir)
        result = stage.run(
            state,
            _llm(workdir, model=model, effort=effort, provider=provider),
            target,
            company=company,
            posting_file=posting,
            report=_step,
        )
    except (StageError, LLMError, providers.ProviderError, PromptError, FileNotFoundError) as exc:
        _fail(exc)
    else:
        console.print(
            f"[green]{result.company}[/green] — {result.role_title} "
            f"({result.org_type}, {result.seniority}); "
            f"{len(result.claims)} claims, {len(result.requirements)} requirements"
        )


@app.command()
def profile(
    cv: str = typer.Argument(..., help="Your CV: .json, .md, .txt or .pdf"),
    workdir: Path = WorkdirOpt,
    notes: Optional[str] = typer.Option(None, "--notes", help="Extra context about you, as a file."),
    model: Optional[str] = ModelOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Parse your CV. Writes profile.json."""
    from .stages import profile as stage

    try:
        state = RunState.load_or_create(workdir)
        result = stage.run(
            state, _llm(workdir, model=model, provider=provider), cv, notes_path=notes, report=_step
        )
    except (StageError, LLMError, providers.ProviderError, PromptError, FileNotFoundError, ValueError) as exc:
        _fail(exc)
    else:
        console.print(
            f"[green]parsed[/green] {len(result.skills)} skills, "
            f"{len(result.projects)} projects"
        )
        for item in result.inconsistencies:
            console.print(f"[yellow]worth deciding before the call:[/yellow] {item.note}")


@app.command()
def match(
    workdir: Path = WorkdirOpt,
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Skip the probe loop; the card is marked provisional."),
    notes: Optional[str] = typer.Option(None, "--notes", help="Extra context up front, as a file."),
    model: Optional[str] = ModelOpt,
    effort: Optional[str] = EffortOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Score the role against you. Writes match.json and 02-fit.md."""
    from .cards import terminal_lines
    from .stages import match as stage

    try:
        state = RunState.load(workdir)
        result = stage.run(
            state,
            _llm(workdir, needs=("recon.json", "profile.json"), model=model, effort=effort, provider=provider),
            interactive=not non_interactive,
            notes_path=notes,
            report=_report,
            ask=_ask,
        )
        recon_data = state.read_json("recon.json")
    except (StageError, LLMError, providers.ProviderError, PromptError, FileNotFoundError) as exc:
        _fail(exc)
    else:
        console.print()
        _card(
            terminal_lines(
                result,
                role=recon_data.get("role_title", ""),
                company=recon_data.get("company", ""),
            )
        )


@app.command()
def gate(
    workdir: Path = WorkdirOpt,
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Take the recommendation without asking."),
    assume: Optional[str] = typer.Option(None, "--assume", help="proceed|declined — record a decision without asking."),
    model: Optional[str] = ModelOpt,
    effort: Optional[str] = EffortOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Should you apply? Records your decision in run.json."""
    from .stages import gate as stage

    try:
        state = RunState.load(workdir)
        _, decision = stage.run(
            state,
            _llm(workdir, needs=("recon.json", "match.json"), model=model, effort=effort, provider=provider),
            interactive=not non_interactive,
            assume=assume,
            report=_report,
            confirm=_confirm,
        )
    except (StageError, LLMError, providers.ProviderError, PromptError) as exc:
        _fail(exc)
    else:
        if decision != "proceed":
            raise typer.Exit(code=0)


@app.command()
def playbook(
    workdir: Path = WorkdirOpt,
    force: bool = typer.Option(False, "--force", help="Build it even though you declined at the gate."),
    model: Optional[str] = ModelOpt,
    effort: Optional[str] = EffortOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Questions and reference answers. Writes playbook.json and 03-playbook.md."""
    from .stages import playbook as stage

    try:
        state = RunState.load(workdir)
        result = stage.run(
            state,
            _llm(
                workdir,
                needs=("recon.json", "profile.json", "match.json"),
                model=model,
                effort=effort,
                provider=provider,
            ),
            force=force,
            report=_step,
        )
    except (StageError, LLMError, providers.ProviderError, PromptError) as exc:
        _fail(exc)
    else:
        techs = ", ".join(t.technology for t in result.technologies)
        console.print(f"[green]playbook[/green] — {techs or 'no technical core'}")


@app.command()
def render(
    workdir: Path = WorkdirOpt,
    audio: Optional[bool] = typer.Option(None, "--audio/--no-audio", help="Render narration scripts and synthesize them."),
    tts_backend: Optional[str] = typer.Option(None, "--tts-backend", help="auto|kokoro|say|none"),
    voice: Optional[str] = typer.Option(None, "--voice"),
    rate: Optional[int] = typer.Option(None, "--rate", help="Words per minute."),
    model: Optional[str] = ModelOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Diagrams, the index, fit.html, and optionally audio."""
    from .stages import render as stage

    try:
        state = RunState.load(workdir)
        stage.run(
            state,
            _llm(
                workdir,
                needs=("recon.json", "match.json"),
                model=model,
                provider=provider,
                tts_backend=tts_backend,
                voice=voice,
                rate=rate,
            ),
            audio=audio,
            report=_step,
        )
    except (StageError, LLMError, providers.ProviderError, PromptError) as exc:
        _fail(exc)
    else:
        console.print(f"[green]done[/green] — open {workdir / '00-README.md'}")


@app.command()
def run(
    target: str = typer.Argument(..., help="Job posting URL, or a path to the saved posting."),
    cv: str = typer.Option(..., "--cv", help="Your CV: .json, .md, .txt or .pdf"),
    workdir: Path = WorkdirOpt,
    company: Optional[str] = typer.Option(None, "--company"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Extra context about you, as a file."),
    non_interactive: bool = typer.Option(False, "--non-interactive"),
    audio: Optional[bool] = typer.Option(
        None,
        "--audio/--no-audio",
        help="Skip the question and decide up front.",
    ),
    force: bool = typer.Option(False, "--force", help="Build the playbook even on a declined gate."),
    model: Optional[str] = ModelOpt,
    effort: Optional[str] = EffortOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """All six stages, in order."""
    from .cards import terminal_lines
    from .stages import gate as gate_stage
    from .stages import match as match_stage
    from .stages import playbook as playbook_stage
    from .stages import profile as profile_stage
    from .stages import recon as recon_stage
    from .stages import render as render_stage

    interactive = not non_interactive
    try:
        state = RunState.load_or_create(workdir)
        llm = _llm(workdir, model=model, effort=effort, provider=provider)

        console.rule("[bold]recon")
        recon_result = recon_stage.run(
            state, llm, target, company=company, report=_step
        )

        console.rule("[bold]profile")
        profile_result = profile_stage.run(
            state, llm, cv, notes_path=notes, report=_step
        )
        for item in profile_result.inconsistencies:
            console.print(f"[yellow]decide before the call:[/yellow] {item.note}")

        console.rule("[bold]fit")
        match_result = match_stage.run(
            state, llm, interactive=interactive, report=_report, ask=_ask
        )
        console.print()
        _card(
            terminal_lines(
                match_result,
                role=recon_result.role_title,
                company=recon_result.company,
            )
        )

        console.rule("[bold]decision")
        _, decision = gate_stage.run(
            state,
            llm,
            interactive=interactive,
            report=_report,
            confirm=_confirm,
        )
        if decision != "proceed" and not force:
            raise typer.Exit(code=0)

        console.rule("[bold]playbook")
        playbook_stage.run(state, llm, force=force, report=_step)

        console.rule("[bold]render")
        render_stage.run(
            state, llm, audio=_want_audio(audio, llm, interactive), report=_step
        )
    except typer.Exit:
        raise
    except (StageError, LLMError, providers.ProviderError, PromptError, FileNotFoundError, ValueError) as exc:
        _fail(exc)
    else:
        console.print()
        console.print(f"[green]done[/green] — open {workdir / '00-README.md'}")


@app.command()
def version() -> None:
    """Print the version, and what has actually been tested."""
    console.print(f"pitches-peaches {__version__}")
    console.print()
    console.print(f"[bold]Verified:[/bold] {VERIFIED_PROVIDER}/{VERIFIED_MODEL}, "
                  "full pipeline, non-interactive, no audio.")
    console.print("[bold]Unproven[/bold] (written and unit tested, never run live):")
    from . import UNVERIFIED_PATHS

    for path in UNVERIFIED_PATHS:
        console.print(f"  - {path}")
    console.print()
    console.print("[dim]Details: DEBRIEF.md[/dim]")


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:  # pragma: no cover
        err.print("\n[dim]stopped[/dim]")
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
