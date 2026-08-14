"""The `peaches` command.

Six stages, each independently runnable and resumable, plus `init` to scaffold
and `run` to do the lot in order.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from . import (
    UNVERIFIED_PATHS,
    VERIFIED_MODEL,
    VERIFIED_PATHS,
    VERIFIED_PROVIDER,
    __version__,
    is_verified,
)
from .config import (
    CONFIG_FILE,
    CONFIG_TEMPLATE,
    GITIGNORE_TEMPLATE,
    Config,
    any_key_present,
    load_dotenv,
)
from . import cvs as cv_cache
from . import providers
from .llm import LLM, LLMError
from .prompts import PromptError
from .state import RunState, StageError
from .workspace import (
    CV_SUFFIXES,
    GITIGNORE_WORKSPACE,
    Application,
    CV,
    Workspace,
    WorkspaceError,
    slugify,
)

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
# Errors name the command that fixes them, so nothing here may be re-wrapped:
# rich breaking "peaches recon" across two lines costs the reader a paste.
err = Console(stderr=True, soft_wrap=True)

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


@dataclass
class Ctx:
    """Where this invocation reads config, and where it writes artifacts.

    Two shapes, and the whole point is that the stages cannot tell them apart:

    ``-C somewhere``       one directory holding everything, as it always was.
    a workspace            ``applications/NN-slug/by-cv/<name>/``, with the
                           posting-scoped artifacts one level up so every CV
                           shares the recon that was paid for once.
    """

    state: RunState
    #: Where ``peaches.toml`` and ``.env`` are read from — the workspace root
    #: when there is one, so config is written once and inherited by every run.
    config_dir: Path
    workspace: Workspace | None = None
    application: Application | None = None
    cv: CV | None = None

    @property
    def in_workspace(self) -> bool:
        return self.workspace is not None


def _cfg(workdir: Path, **overrides) -> Config:
    load_dotenv(workdir)
    return Config.load(workdir, **overrides)


def _llm(
    workdir: Path,
    *,
    state: RunState | None = None,
    needs: tuple[str, ...] = (),
    **overrides,
) -> LLM:
    """The composition root: resolve everything once, then hand it down.

    ``workdir`` is where config is read from, which in a workspace is the root
    rather than the run directory — so ``peaches.toml`` is written once and
    inherited. ``state`` is the run being checked, which is not the same
    directory and, for a shared recon, not even the same level.

    Order matters for the error the user actually sees. A missing upstream
    artifact is both more likely and more actionable than a credential
    problem, so it is checked first; then provider resolution, which reports
    a missing key, a wrong-provider key, or a missing SDK with the exact fix.
    """
    config = _cfg(workdir, **overrides)
    if needs:
        (state or RunState.load(workdir)).require(*needs)

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


# -- resolving where this invocation works -----------------------------------


def _workspace(workdir: Optional[Path]) -> Workspace | None:
    """A workspace, unless ``-C`` asked for one directory holding everything.

    ``-C`` is the original contract and stays exactly as documented: it names a
    run directory, and nothing above it is consulted. Without it we look upward
    from the current directory the way git does, so a stage command works from
    inside a run directory without repeating where the workspace is.
    """
    if workdir is not None:
        return None
    return Workspace.discover(Path.cwd())


def _has_key(config_dir: Path) -> bool:
    load_dotenv(config_dir)
    return any_key_present()


def _ensure_key(config_dir: Path) -> bool:
    """Offer to write a provider key into ``.env``. True once one is available.

    The key is read without echo and written to a file only this user can read.
    It is never printed back, never passed on a command line where a shell would
    keep it in history, and goes nowhere but the provider it belongs to.
    """
    if _has_key(config_dir):
        return True

    console.print()
    console.print("[bold]No provider key yet.[/bold] One is all this tool ever needs.")
    options = list(providers.all_providers())
    for index, provider in enumerate(options, 1):
        console.print(f"  [bold]{index}[/bold]  {provider.name:<10} {provider.env_key}")
    console.print()
    console.print(
        "[dim]It is written to .env in this workspace, readable only by you, and "
        "sent only to that provider.[/dim]"
    )

    try:
        picked = typer.prompt("Which provider", default="1").strip()
        provider = options[int(picked) - 1] if picked.isdigit() else next(
            p for p in options if p.name == picked
        )
        value = typer.prompt(f"Paste your {provider.env_key}", hide_input=True).strip()
    except (EOFError, KeyboardInterrupt, IndexError, StopIteration, ValueError):
        console.print("[dim]nothing written[/dim]")
        return False

    if not value:
        return False

    env = config_dir / ".env"
    existing = env.read_text(encoding="utf-8") if env.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    env.write_text(f"{existing}{provider.env_key}={value}\n", encoding="utf-8")
    env.chmod(0o600)
    os.environ[provider.env_key] = value
    console.print(f"[green]saved[/green] {provider.env_key} to {env}  [dim](0600)[/dim]")
    return True


def _ensure_cv(workspace: Workspace) -> CV | None:
    """Point at a CV anywhere on disk; it is copied into the workspace."""
    available = workspace.cvs()
    if available:
        return _pick_cv(workspace, None)

    console.print()
    console.print("[bold]No CV yet.[/bold] Point me at one and I will copy it in.")
    console.print("[dim].pdf, .json, .md or .txt — the original is not touched.[/dim]")
    try:
        given = typer.prompt("Path to your CV").strip().strip("'\"")
    except (EOFError, KeyboardInterrupt):
        return None

    source = Path(given).expanduser()
    if not source.exists():
        console.print(f"[red]no file at {source}[/red]")
        return None
    if source.suffix.lower() not in CV_SUFFIXES:
        console.print(f"[red]cannot read a CV from {source.suffix}[/red]")
        return None

    name = typer.prompt("Call it", default=slugify(source.stem) or "cv").strip()
    workspace.cvs_dir.mkdir(parents=True, exist_ok=True)
    target = workspace.cvs_dir / f"{name}{source.suffix}"
    target.write_bytes(source.read_bytes())
    console.print(f"[green]copied[/green] {source.name} → {target}")
    return workspace.cv(name)


def _ask_posting(workspace: Workspace) -> tuple[str | None, Application | None]:
    """A URL, a file, or the text itself. Returns (target, existing application)."""
    console.print()
    console.print("[bold]The job posting.[/bold]")
    console.print("  [bold]1[/bold]  a link")
    console.print("  [bold]2[/bold]  a file on disk")
    console.print("  [bold]3[/bold]  paste the text")
    try:
        choice = typer.prompt("Which", default="1").strip()
    except (EOFError, KeyboardInterrupt):
        return None, None

    if choice == "3":
        console.print()
        console.print("[dim]Paste it, then press Ctrl-D on a blank line.[/dim]")
        text = sys.stdin.read().strip()
        if not text:
            console.print("[red]nothing pasted[/red]")
            return None, None
        application = workspace.new_application_from_text(text)
        console.print(
            f"[green]saved[/green] {len(text.split()):,} words → "
            f"{application.path.name}/posting.txt"
        )
        # Returned as "not existing" on purpose: it was created a line ago, and
        # the caller reports a found application as one you are continuing.
        # The stored path is matched again downstream, so it still resolves here.
        return application.target, None

    try:
        given = typer.prompt(
            "Link" if choice == "1" else "Path to the posting"
        ).strip().strip("'\"")
    except (EOFError, KeyboardInterrupt):
        return None, None
    if not given:
        return None, None

    if not given.startswith(("http://", "https://")):
        path = Path(given).expanduser()
        if not path.exists():
            console.print(f"[red]no file at {path}[/red]")
            return None, None
        given = str(path.resolve())

    return given, workspace.find_by_target(given)


def _check_credential(config_dir: Path) -> None:
    """Raise the usual credential error before anything permanent happens.

    Deliberately reuses ``providers.resolve`` rather than a cheaper test, so
    the reader gets the one message that already names every key, the flag for
    each provider, and the exact ``.env`` path to create.
    """
    config = _cfg(config_dir)
    providers.resolve(config.provider, model=config.model, workdir=config_dir)


def _pick_cv(
    workspace: Workspace,
    name: Optional[str],
    *,
    application: Application | None = None,
    interactive: bool = True,
) -> CV:
    """One CV is picked silently; several are offered; none names the fix."""
    if name:
        return workspace.cv(name)

    available = workspace.cvs()
    if not available:
        raise WorkspaceError(
            f"no CVs in {workspace.cvs_dir} yet.\nRun: peaches cv add <path to your CV>"
        )
    if len(available) == 1:
        return available[0]

    # Already used for this application? Then that is the obvious one.
    if application:
        used = application.cvs()
        for candidate in available:
            if candidate.name in used:
                return candidate

    names = ", ".join(candidate.name for candidate in available)
    if not interactive:
        raise WorkspaceError(
            f"several CVs to choose from ({names}), and nothing to ask.\n"
            "Run: peaches run <posting> --cv <name>"
        )

    console.print("\n[bold]Which CV?[/bold]")
    for index, candidate in enumerate(available, 1):
        state = candidate.state()
        note = "" if state == "ready" else f"  [dim]({state})[/dim]"
        console.print(f"  [bold]{index}[/bold]  {candidate.name}{note}")
    try:
        chosen = typer.prompt("Number", default="1")
    except (EOFError, KeyboardInterrupt):
        raise WorkspaceError(f"no CV chosen. Pass --cv <name> — one of: {names}")
    if chosen.strip().isdigit() and 1 <= int(chosen) <= len(available):
        return available[int(chosen) - 1]
    return workspace.cv(chosen.strip())


def _resolve_run(
    target: Optional[str],
    cv_name: Optional[str],
    app_id: Optional[int],
    workdir: Optional[Path],
    *,
    interactive: bool = True,
    create: bool = False,
) -> Ctx:
    """Work out which directory this invocation writes to, and say so out loud.

    Nothing here is remembered between invocations — there is no current-app
    pointer to get out of sync with what the reader thinks is selected. The
    application is named by ``--app``, or found from the posting, or created;
    whichever happened is printed before any work starts.

    ``create`` separates the commands that start a pipeline from the ones that
    continue it. A stage run somewhere nothing has happened yet must say so and
    name the command that starts one — creating an empty run and then
    complaining about a missing dependency answers a question nobody asked.
    """
    workspace = _workspace(workdir)
    if workspace is None:
        root = Path(workdir or ".")
        state = RunState.load_or_create(root) if create else RunState.load(root)
        return Ctx(state=state, config_dir=root)

    application: Application | None = None
    if app_id is not None:
        application = workspace.application(app_id)
    elif target:
        application = workspace.find_by_target(target)  # None means a new one
    else:
        application = _most_recent(workspace)
        console.print(f"[dim]resuming application {application.id:02d}[/dim]")

    # Which CV, before anything is created or any credential is examined. A
    # missing or ambiguous CV is both likelier and more actionable than a
    # missing key — the same order ``_llm`` already argues for.
    chosen = _pick_cv(
        workspace, cv_name, application=application, interactive=interactive
    )

    if application is None:
        # An id is claimed permanently and never handed out again, so it is not
        # something to spend on a run that is about to stop anyway. The
        # commonest reason it stops is the very first one: no key yet.
        _check_credential(workspace.root)
        application = workspace.new_application(target)
        console.print(f"[green]new application[/green] {application.id:02d}")
    console.print(
        f"[dim]application {application.id:02d} · {application.display()} "
        f"· cv {chosen.name}[/dim]"
    )
    run_dir = application.run_dir(chosen.name)
    if create:
        state = RunState.load_or_create(run_dir, shared=application.path)
    elif (run_dir / "run.json").exists():
        state = RunState.load(run_dir, shared=application.path)
    else:
        raise WorkspaceError(
            f"application {application.id:02d} has not been started with "
            f"{chosen.name} yet.\nRun: peaches run --app {application.id} "
            f"--cv {chosen.name}"
        )

    return Ctx(
        state=state,
        config_dir=workspace.root,
        workspace=workspace,
        application=application,
        cv=chosen,
    )


def _most_recent(workspace: Workspace) -> Application:
    """The application touched last — and the caller always prints which.

    Convenience without a stored pointer: nothing persists a selection, so
    there is no hidden state to drift out of step with what the reader thinks
    they are working on.
    """
    applications = workspace.applications()
    if not applications:
        raise WorkspaceError(
            "no applications yet.\nRun: peaches run <posting url or file>"
        )
    return max(applications, key=lambda item: item.path.stat().st_mtime)


def _recon_from_disk(state: RunState):
    from .models import Recon

    return Recon.model_validate(state.read_json("recon.json"))


def _bank_answers(ctx: Ctx, interactive: bool) -> None:
    """Offer to keep what the reader typed, so the next application reuses it.

    Probe answers are CV material they simply never wrote down. Discarding them
    into one run directory means being asked the same question on every future
    application, and a thinner card each time.
    """
    if ctx.cv is None or not interactive or not ctx.state.has("profile.json"):
        return
    from .models import Profile

    profile = Profile.model_validate(ctx.state.read_json("profile.json"))
    known = cv_cache.load_extra(ctx.cv)
    fresh = [note for note in cv_cache.answers_in(profile) if note not in known]
    if not fresh:
        return

    console.print()
    if _confirm_with_default(
        f"You told us {len(fresh)} thing(s) that are not in {ctx.cv.path.name}. "
        "Keep them for future applications?",
        True,
    ):
        cv_cache.save_extra(ctx.cv, fresh)
        console.print(f"[dim]kept — {ctx.cv.name} carries them from now on[/dim]")


def _adopt_shared_recon(state: RunState, application: Application, cv_name: str) -> None:
    """Copy a sibling's recon record into this run's ``run.json``.

    The artifacts are shared, so this run legitimately did not research
    anything. Leaving ``run.json`` silent about a stage whose output it depends
    on is the kind of quiet inaccuracy the rest of this project keeps writing
    documents about, so the record is copied and marked as shared.
    """
    if state.ran("recon") or not state.has("recon.json"):
        return
    for sibling in application.cvs():
        if sibling == cv_name:
            continue
        record = application.run_dir(sibling) / "run.json"
        if not record.exists():
            continue
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "recon" in data.get("stages", {}):
            state.adopt("recon", data["stages"]["recon"])
            return


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


def _confirm_with_default(question: str, default: bool) -> bool:
    """The shape the CV cache asks for. A refused prompt is always a no."""
    try:
        return typer.confirm(question, default=default)
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
        # Two costs, and conflating them is the reason this wording changed:
        # the rewrite is the model call, the voice is free. Somebody reasonably
        # read "synthesized with say — one model call" as paying for the .wav.
        from .stages.render import NARRATED

        narrated = ", ".join(name.removesuffix(".md") for name in NARRATED)
        console.print(
            f"[dim]Narrated: {narrated}. Not the fit card — it is a table, and "
            "a table read aloud is worse than useless.[/dim]"
        )
        console.print(
            f"[dim]Each is rewritten for the ear first — acronyms expanded, "
            f"tables and links removed, pauses marked. That is "
            f"{len(NARRATED)} model calls, and the scripts are kept and "
            f"reused.[/dim]"
        )
        upgrade = (
            backend.name != "kokoro" and tts.kokoro_is_only_missing_its_model()
        )
        voice = "kokoro, once its pronunciation model is installed" if upgrade else backend.name
        console.print(
            f"[dim]Turning those scripts into audio is free and local, with "
            f"{voice}. It takes a few minutes per document.[/dim]"
        )
    try:
        return typer.confirm("Render narration audio?", default=False)
    except (EOFError, KeyboardInterrupt):
        return False


# -- options -----------------------------------------------------------------

WorkdirOpt = typer.Option(
    None,
    "--workdir",
    "-C",
    help="One run directory, holding everything. Bypasses the workspace.",
    show_default=".",
)
AppOpt = typer.Option(None, "--app", help="Application id, as shown by `peaches ls`.")
CvOpt = typer.Option(None, "--cv", help="Which CV, by name. See `peaches cv ls`.")
ModelOpt = typer.Option(None, "--model", help="Override the model id.")
ProviderOpt = typer.Option(
    None, "--provider", help="anthropic|openai|gemini|auto"
)
EffortOpt = typer.Option(None, "--effort", help="low|medium|high|xhigh|max")


# -- commands ----------------------------------------------------------------


@app.command()
def init(workdir: Path = WorkdirOpt) -> None:
    """Scaffold a workspace: config, an example CV, and a .gitignore.

    With ``-C`` this scaffolds a single run directory instead, which is what
    it always did.
    """
    if workdir is None:
        _init_workspace(Path.cwd())
        return

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


def _init_workspace(root: Path) -> None:
    workspace = Workspace.create(root)

    written = []
    for path, content in (
        (root / CONFIG_FILE, CONFIG_TEMPLATE),
        (root / ".gitignore", GITIGNORE_WORKSPACE),
        (
            root / "cv.example.json",
            json.dumps(CV_EXAMPLE, indent=2, ensure_ascii=False) + "\n",
        ),
    ):
        if path.exists():
            continue
        path.write_text(content, encoding="utf-8")
        written.append(path.name)

    console.print(f"[green]workspace ready[/green] in {workspace.root}")
    console.print("  [dim]cvs/           your CVs; parsed once, reused everywhere[/dim]")
    console.print("  [dim]applications/  one directory per posting[/dim]")
    for name in written:
        console.print(f"  wrote {name}")

    console.print()
    _cfg(root)  # loads .env so the check below sees any key already there
    if not any_key_present():
        console.print("Set a provider key. Any one of:")
        for provider in providers.all_providers():
            console.print(f"  [bold]export {provider.env_key}=...[/bold]")
        console.print()
    console.print("Then:")
    console.print("  [bold]peaches cv add ~/cv.pdf[/bold]")
    console.print("  [bold]peaches run https://the-job-posting[/bold]")


def _stage_reached(application: Application) -> str:
    """The furthest stage any CV under this application has completed."""
    order = ("recon", "profile", "match", "gate", "playbook", "render")
    furthest = ""
    declined = False
    for name in application.cvs():
        record = application.run_dir(name) / "run.json"
        if not record.exists():
            continue
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for stage in order:
            if stage in data.get("stages", {}):
                furthest = stage
        if (data.get("decision") or {}).get("decision") not in (None, "proceed"):
            declined = True
    if declined and furthest in ("gate", ""):
        return "declined"
    return furthest or "new"


@app.command("ls")
def list_applications(workdir: Path = WorkdirOpt) -> None:
    """Every application in this workspace, and how far each one got."""
    workspace = _workspace(workdir)
    if workspace is None:
        _fail(WorkspaceError("not in a workspace.\nRun: peaches init"))

    applications = workspace.applications()
    if not applications:
        console.print("[dim]no applications yet[/dim]")
        console.print("  [bold]peaches run https://the-job-posting[/bold]")
        return

    width = max(len(a.display()) for a in applications)
    for item in applications:
        used = ", ".join(item.cvs()) or "[dim]no CV yet[/dim]"
        console.print(
            f"  [bold]{item.id:02d}[/bold]  {item.display():<{width}}  "
            f"[dim]{_stage_reached(item):<8}[/dim]  {used}",
            highlight=False,
        )
    console.print()
    console.print("[dim]peaches resume <id>, or peaches run <posting>[/dim]")


cv_app = typer.Typer(help="The CVs in this workspace.", no_args_is_help=True)
app.add_typer(cv_app, name="cv")


@cv_app.command("ls")
def cv_list(workdir: Path = WorkdirOpt) -> None:
    """List your CVs and whether each one has been parsed."""
    workspace = _workspace(workdir)
    if workspace is None:
        _fail(WorkspaceError("not in a workspace.\nRun: peaches init"))
    try:
        available = workspace.cvs()
    except WorkspaceError as exc:
        _fail(exc)

    if not available:
        console.print("[dim]no CVs yet[/dim]")
        console.print("  [bold]peaches cv add ~/cv.pdf[/bold]")
        return

    explain = {
        "ready": "[green]parsed[/green]",
        "stale": "[yellow]changed since it was parsed[/yellow]",
        "unparsed": "[dim]not parsed yet[/dim]",
    }
    width = max(len(item.name) for item in available)
    for item in available:
        console.print(
            f"  {item.name:<{width}}  {explain[item.state()]}  [dim]{item.path.name}[/dim]"
        )


@cv_app.command("add")
def cv_add(
    path: Path = typer.Argument(..., help="Your CV: .json, .md, .txt or .pdf"),
    name: Optional[str] = typer.Option(None, "--name", help="Defaults to the filename."),
    workdir: Path = WorkdirOpt,
) -> None:
    """Copy a CV into the workspace. Free — parsing happens on first use."""
    workspace = _workspace(workdir)
    if workspace is None:
        _fail(WorkspaceError("not in a workspace.\nRun: peaches init"))

    source = path.expanduser()
    if not source.exists():
        _fail(FileNotFoundError(f"no CV at {source}"))

    target = workspace.cvs_dir / f"{name or source.stem}{source.suffix}"
    if target.exists() and target.resolve() != source.resolve():
        _fail(WorkspaceError(f"{target.name} is already in {workspace.cvs_dir}."))
    workspace.cvs_dir.mkdir(parents=True, exist_ok=True)
    if target.resolve() != source.resolve():
        target.write_bytes(source.read_bytes())

    console.print(f"[green]added[/green] {target.stem}  [dim]{target}[/dim]")
    console.print(
        "[dim]Not parsed yet — that costs a model call, so it happens on first "
        "use and asks first.[/dim]"
    )


@cv_app.command("parse")
def cv_parse(
    name: Optional[str] = typer.Argument(None, help="Which CV. Omit when there is one."),
    workdir: Path = WorkdirOpt,
    reparse: bool = typer.Option(False, "--reparse", help="Parse again even if unchanged."),
    model: Optional[str] = ModelOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Parse a CV now, rather than on first use."""
    workspace = _workspace(workdir)
    if workspace is None:
        _fail(WorkspaceError("not in a workspace.\nRun: peaches init"))

    try:
        chosen = _pick_cv(workspace, name)
        llm = _llm(workspace.root, model=model, provider=provider)
        profile, _ = cv_cache.ensure_parsed(
            chosen,
            llm,
            confirm=_confirm_with_default,
            report=_step,
            reparse=True if reparse else None,
        )
    except (WorkspaceError, StageError, LLMError, providers.ProviderError,
            PromptError, FileNotFoundError, ValueError) as exc:
        _fail(exc)
    else:
        console.print(
            f"[green]parsed[/green] {chosen.name} — {len(profile.skills)} skills, "
            f"{len(profile.projects)} projects"
        )
        for item in profile.inconsistencies:
            console.print(f"[yellow]worth deciding before the call:[/yellow] {item.note}")


@app.command()
def recon(
    target: str = typer.Argument(..., help="Job posting URL, or a path to the saved posting."),
    cv: Optional[str] = CvOpt,
    application: Optional[int] = AppOpt,
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
        ctx = _resolve_run(target, cv, application, workdir, create=True)
        result = stage.run(
            ctx.state,
            _llm(ctx.config_dir, model=model, effort=effort, provider=provider),
            target,
            company=company,
            posting_file=posting,
            report=_step,
        )
    except (WorkspaceError, StageError, LLMError, providers.ProviderError, PromptError, FileNotFoundError) as exc:
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
    application: Optional[int] = AppOpt,
    workdir: Path = WorkdirOpt,
    notes: Optional[str] = typer.Option(None, "--notes", help="Extra context about you, as a file."),
    model: Optional[str] = ModelOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Parse your CV into this run. Writes profile.json.

    In a workspace, prefer ``peaches cv add`` and ``peaches cv parse`` — those
    put the parse in the shared cache, so every application reuses it.
    """
    from .stages import profile as stage

    try:
        ctx = _resolve_run(None, None, application, workdir, create=True)
        result = stage.run(
            ctx.state,
            _llm(ctx.config_dir, model=model, provider=provider),
            cv,
            notes_path=notes,
            report=_step,
        )
    except (WorkspaceError, StageError, LLMError, providers.ProviderError, PromptError, FileNotFoundError, ValueError) as exc:
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
    cv: Optional[str] = CvOpt,
    application: Optional[int] = AppOpt,
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

    interactive = not non_interactive
    try:
        ctx = _resolve_run(None, cv, application, workdir, interactive=interactive)
        result = stage.run(
            ctx.state,
            _llm(
                ctx.config_dir,
                state=ctx.state,
                needs=("recon.json", "profile.json"),
                model=model,
                effort=effort,
                provider=provider,
            ),
            interactive=interactive,
            notes_path=notes,
            report=_report,
            ask=_ask,
        )
        recon_data = ctx.state.read_json("recon.json")
    except (WorkspaceError, StageError, LLMError, providers.ProviderError, PromptError, FileNotFoundError) as exc:
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
        _bank_answers(ctx, interactive)


@app.command()
def gate(
    cv: Optional[str] = CvOpt,
    application: Optional[int] = AppOpt,
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
        ctx = _resolve_run(None, cv, application, workdir, interactive=not non_interactive)
        _, decision = stage.run(
            ctx.state,
            _llm(
                ctx.config_dir,
                state=ctx.state,
                needs=("recon.json", "match.json"),
                model=model,
                effort=effort,
                provider=provider,
            ),
            interactive=not non_interactive,
            assume=assume,
            report=_report,
            confirm=_confirm,
        )
    except (WorkspaceError, StageError, LLMError, providers.ProviderError, PromptError) as exc:
        _fail(exc)
    else:
        if decision != "proceed":
            raise typer.Exit(code=0)


@app.command()
def playbook(
    cv: Optional[str] = CvOpt,
    application: Optional[int] = AppOpt,
    workdir: Path = WorkdirOpt,
    force: bool = typer.Option(False, "--force", help="Build it even though you declined at the gate."),
    model: Optional[str] = ModelOpt,
    effort: Optional[str] = EffortOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Questions and reference answers. Writes playbook.json and 03-playbook.md."""
    from .stages import playbook as stage

    try:
        ctx = _resolve_run(None, cv, application, workdir)
        result = stage.run(
            ctx.state,
            _llm(
                ctx.config_dir,
                state=ctx.state,
                needs=("recon.json", "profile.json", "match.json"),
                model=model,
                effort=effort,
                provider=provider,
            ),
            force=force,
            report=_step,
        )
    except (WorkspaceError, StageError, LLMError, providers.ProviderError, PromptError) as exc:
        _fail(exc)
    else:
        techs = ", ".join(t.technology for t in result.technologies)
        console.print(f"[green]playbook[/green] — {techs or 'no technical core'}")


@app.command()
def render(
    cv: Optional[str] = CvOpt,
    application: Optional[int] = AppOpt,
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
        ctx = _resolve_run(None, cv, application, workdir)
        stage.run(
            ctx.state,
            _llm(
                ctx.config_dir,
                state=ctx.state,
                needs=("recon.json", "match.json"),
                model=model,
                provider=provider,
                tts_backend=tts_backend,
                voice=voice,
                rate=rate,
            ),
            audio=audio,
            report=_step,
            confirm=_confirm_with_default,
        )
    except (WorkspaceError, StageError, LLMError, providers.ProviderError, PromptError) as exc:
        _fail(exc)
    else:
        console.print(f"[green]done[/green] — open {ctx.state.workdir / '00-README.md'}")


@app.command()
def run(
    target: Optional[str] = typer.Argument(None, help="Job posting URL, or a path to the saved posting."),
    cv: Optional[str] = typer.Option(None, "--cv", help="Which CV. A name in the workspace, or a path with -C."),
    application: Optional[int] = AppOpt,
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
    reparse: Optional[bool] = typer.Option(
        None, "--reparse/--use-cached", help="Pre-answer the prompt for a CV that has changed."
    ),
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
        ctx = _resolve_run(
            target, cv, application, workdir, interactive=interactive, create=True
        )
        state = ctx.state
        llm = _llm(ctx.config_dir, model=model, effort=effort, provider=provider)
        target = target or (ctx.application.target if ctx.application else None)
        if not target:
            raise WorkspaceError(
                "no posting to work from. Pass the URL, or --app <id> to resume one."
            )

        console.rule("[bold]profile")
        if ctx.cv is not None:
            parsed, source = cv_cache.resolved(
                ctx.cv,
                llm,
                ask=_ask if interactive else None,
                confirm=_confirm_with_default if interactive else None,
                report=_step,
                notes_path=notes,
                reparse=reparse,
            )
            profile_stage.write(state, parsed, source, ctx.cv.path)
            profile_result = parsed
        else:
            profile_result = profile_stage.run(
                state, llm, cv, notes_path=notes, report=_step
            )
        for item in profile_result.inconsistencies:
            console.print(f"[yellow]decide before the call:[/yellow] {item.note}")

        console.rule("[bold]recon")
        if state.has("recon.json"):
            # Another CV under this application already paid for it.
            _adopt_shared_recon(state, ctx.application, ctx.cv.name)
            recon_result = _recon_from_disk(state)
            _step(f"reusing the research for {recon_result.company}")
        else:
            recon_result = recon_stage.run(
                state, llm, target, company=company, report=_step
            )

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
        _bank_answers(ctx, interactive)

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
            state,
            llm,
            audio=_want_audio(audio, llm, interactive),
            report=_step,
            confirm=_confirm_with_default if interactive else None,
        )
    except typer.Exit:
        raise
    except (WorkspaceError, StageError, LLMError, providers.ProviderError, PromptError, FileNotFoundError, ValueError) as exc:
        _fail(exc)
    else:
        console.print()
        console.print(f"[green]done[/green] — open {ctx.state.workdir / '00-README.md'}")


@app.command()
def start(
    audio: Optional[bool] = typer.Option(None, "--audio/--no-audio"),
    model: Optional[str] = ModelOpt,
    effort: Optional[str] = EffortOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Set everything up and run it, asking for what is missing as it goes.

    The same six stages as ``peaches run``; this only gathers what they need
    first, so nothing has to be arranged by hand before the first run.
    """
    here = Path.cwd()
    workspace = _workspace(None)
    if workspace is None:
        workspace = Workspace.create(here)
        console.print(f"[green]workspace[/green] {workspace.root}")
        for name, content in (
            (CONFIG_FILE, CONFIG_TEMPLATE),
            (".gitignore", GITIGNORE_WORKSPACE),
        ):
            if not (workspace.root / name).exists():
                (workspace.root / name).write_text(content, encoding="utf-8")
    else:
        console.print(f"[dim]workspace: {workspace.root}[/dim]")

    if not _ensure_key(workspace.root):
        _fail(WorkspaceError("no key, so nothing can run yet. Run: peaches start"))

    try:
        chosen = _ensure_cv(workspace)
    except WorkspaceError as exc:
        _fail(exc)
    if chosen is None:
        _fail(WorkspaceError("no CV, so there is nothing to score. Run: peaches start"))
    console.print(f"[dim]cv: {chosen.name}[/dim]")

    target, existing = _ask_posting(workspace)
    if target is None:
        _fail(WorkspaceError("no posting, so there is nothing to research."))
    if existing is not None:
        console.print(
            f"[dim]this posting is already application "
            f"{existing.id:02d} — continuing it[/dim]"
        )

    console.print()
    run(
        target=target,
        cv=chosen.name,
        application=existing.id if existing is not None else None,
        workdir=None,
        company=None,
        notes=None,
        non_interactive=False,
        audio=audio,
        force=False,
        reparse=None,
        model=model,
        effort=effort,
        provider=provider,
    )


@app.command()
def resume(
    application: Optional[int] = typer.Argument(None, help="Which application. Omit for the most recent."),
    cv: Optional[str] = CvOpt,
    non_interactive: bool = typer.Option(False, "--non-interactive"),
    force: bool = typer.Option(False, "--force", help="Build the playbook even on a declined gate."),
    model: Optional[str] = ModelOpt,
    effort: Optional[str] = EffortOpt,
    provider: Optional[str] = ProviderOpt,
) -> None:
    """Continue an application. The pipeline skips whatever is already done."""
    # Every argument is passed explicitly rather than through ctx.invoke, which
    # leaves Typer's OptionInfo sentinels in place of the defaults it did not
    # fill and fails much later, somewhere much less obvious.
    run(
        target=None,
        cv=cv,
        application=application,
        workdir=None,
        company=None,
        notes=None,
        non_interactive=non_interactive,
        audio=None,
        force=force,
        reparse=None,
        model=model,
        effort=effort,
        provider=provider,
    )


@app.command()
def version() -> None:
    """Print the version, and what has actually been tested."""
    console.print(f"pitches-peaches {__version__}")
    console.print()
    console.print(f"[bold]Verified[/bold] on {VERIFIED_PROVIDER}/{VERIFIED_MODEL}:")
    for path in VERIFIED_PATHS:
        console.print(f"  - {path}")
    console.print()
    console.print("[bold]Unproven[/bold] (written and unit tested, never run live):")
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
