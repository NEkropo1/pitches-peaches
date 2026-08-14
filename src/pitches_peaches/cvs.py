"""Parse a CV once, then reuse it — without ever spending money silently.

A CV is parsed once and read by every application that uses it. That is the
whole saving, and it is only safe because of what the cache stores alongside
the profile: the SHA-256 of the file it was parsed from. During a job search
you edit your CV constantly, and scoring someone against a version they have
since rewritten produces a confidently wrong dossier.

One rule governs everything here, and it is the same rule the audio prompt
already follows: **no model call the reader did not ask for happens without a
prompt that names what it costs.** So there are exactly three situations, and
none of them can quietly spend or quietly mislead:

============  ==================================  ==========================
State         Interactive                         ``--non-interactive``
============  ==================================  ==========================
``unparsed``  ask, naming the cost                proceed — the CV was named
``stale``     ask: re-parse, or use the cached    refuse, naming the fix
``ready``     use the cache                       use the cache
============  ==================================  ==========================

The stale refusal is deliberate. Silently re-parsing spends money nobody
approved; silently using the old parse scores the reader against a CV that no
longer exists. Refusing and naming the command is what every dependency error
in this tool already does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .llm import LLM
from .models import Profile
from .stages import profile as profile_stage
from .workspace import CV, WorkspaceError

Reporter = Callable[[str], None]
#: ``(question, default) -> bool``. ``None`` means nobody is there to answer.
Confirm = Callable[[str, bool], bool]

#: Probe answers promoted out of a single application, to be reused everywhere.
EXTRA_SUFFIX = ".extra.json"

#: What ``match`` prefixes a probe answer with in ``Profile.extra_notes``.
ANSWER_PREFIX = "Q:"


def extra_path(cv: CV) -> Path:
    return cv.parsed_dir / f"{cv.name}{EXTRA_SUFFIX}"


def load_extra(cv: CV) -> list[str]:
    """The answer bank: things the reader told us that are not in their CV."""
    path = extra_path(cv)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    notes = data.get("notes", [])
    return [str(note) for note in notes if str(note).strip()]


def save_extra(cv: CV, notes: list[str]) -> None:
    """Add to the answer bank, keeping order and dropping exact repeats."""
    merged = load_extra(cv)
    for note in notes:
        if note not in merged:
            merged.append(note)
    cv.parsed_dir.mkdir(parents=True, exist_ok=True)
    extra_path(cv).write_text(
        json.dumps({"name": cv.name, "notes": merged}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def answers_in(profile: Profile) -> list[str]:
    """The probe answers in a profile, as opposed to everything else in notes."""
    return [note for note in profile.extra_notes if note.strip().startswith(ANSWER_PREFIX)]


#: Words that mark an inconsistency as being about length of career.
_YEARS_WORDS = ("year", "experience", "seniority", "timeline", "yrs")

#: Where a settled figure is stored, so a re-parse cannot lose it.
YEARS_KEY = "years_total"


def years_dispute(profile: Profile) -> str | None:
    """The note about how long they have been working, if the parse raised one."""
    for item in profile.inconsistencies:
        haystack = " ".join([item.note, *item.lines]).lower()
        if any(word in haystack for word in _YEARS_WORDS):
            return item.note
    return None


def settle_years(
    cv: CV,
    profile: Profile,
    *,
    ask: Callable[[str], str] | None,
    report: Reporter = lambda _: None,
) -> Profile:
    """Let the reader state, once, how long they have been doing this.

    The parse is told to record what the CV claims and never to compute a
    replacement, because a figure derived from dated roles measures a different
    thing: people leave work off deliberately — unpaid, unprovable, before the
    CV starts, or on the far side of a gap they would rather explain out loud.

    So when the dates disagree with the sentence, the tool does not pick. It
    asks the one person who knows, takes whatever they say, and remembers it
    against the CV rather than the application — the answer is about them, and
    it is the same answer for every job they apply to.
    """
    settled = _settled_years(cv)
    if settled:
        profile.years_total = settled
        return profile

    note = years_dispute(profile)
    if note is None or ask is None:
        return profile

    report("")
    report(f"  {note}")
    if profile.years_total:
        report(f"  Your CV says: {profile.years_total}")
    answer = ask(
        "How long have you been doing this? Anything you type is taken as true "
        "— press enter to keep what the CV says"
    ).strip()
    if not answer:
        return profile

    profile.years_total = _as_years(answer)
    _remember_years(cv, profile.years_total)
    report(f"  recorded: {profile.years_total}")
    return profile


def _as_years(answer: str) -> str:
    """``8.5`` becomes ``8.5 years``; anything else is kept exactly as typed."""
    try:
        number = float(answer.replace(",", "."))
    except ValueError:
        return answer
    rendered = f"{number:g}"
    return f"{rendered} year" if number == 1 else f"{rendered} years"


def _settled_years(cv: CV) -> str | None:
    path = extra_path(cv)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get(YEARS_KEY) or None
    except json.JSONDecodeError:
        return None


def _remember_years(cv: CV, value: str) -> None:
    path = extra_path(cv)
    data = {"name": cv.name, "notes": load_extra(cv)}
    if path.exists():
        try:
            data.update(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    data[YEARS_KEY] = value
    cv.parsed_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _from_cache(cv: CV) -> tuple[Profile, str]:
    cached = cv.cached() or {}
    profile = Profile.model_validate(cached["profile"])
    source = cv.source_path.read_text(encoding="utf-8") if cv.source_path.exists() else ""
    return profile, source


def _parse_and_cache(
    cv: CV, llm: LLM, *, report: Reporter, notes_path: str | None
) -> tuple[Profile, str]:
    profile, plain = profile_stage.parse_cv(
        llm, cv.path, notes_path=notes_path, report=report
    )
    source = profile_stage.source_text(profile, plain)
    cv.write_cache(profile, source)
    return profile, source


def ensure_parsed(
    cv: CV,
    llm: LLM,
    *,
    confirm: Confirm | None = None,
    report: Reporter = lambda _: None,
    notes_path: str | None = None,
    reparse: bool | None = None,
) -> tuple[Profile, str]:
    """Return ``(profile, source_text)`` for a CV, parsing only if allowed.

    ``confirm`` is ``None`` for a non-interactive run. ``reparse`` pre-answers
    the stale prompt for scripts: ``True`` re-parses, ``False`` accepts the
    cached parse, ``None`` asks.
    """
    state = cv.state()

    if state == "ready" and reparse is not True:
        report(f"using the cached parse of {cv.path.name}")
        return _from_cache(cv)

    if state == "unparsed":
        if confirm is not None and not confirm(
            f"{cv.path.name} has not been parsed yet. That is one model call. Parse it now?",
            True,
        ):
            raise WorkspaceError(
                f"{cv.name} is not parsed, so there is nothing to score against.\n"
                f"Run: peaches cv parse {cv.name}"
            )
        return _parse_and_cache(cv, llm, report=report, notes_path=notes_path)

    # Stale, or an explicit --reparse.
    if reparse is None and confirm is None:
        raise WorkspaceError(
            f"{cv.path.name} has changed since it was parsed, so the cached "
            "profile no longer describes it.\n"
            f"Run: peaches cv parse {cv.name} --reparse"
        )
    if reparse is None:
        reparse = confirm(
            f"{cv.path.name} has changed since it was parsed. Re-parse it? "
            "That is one model call. Answering no uses the older parse.",
            True,
        )
    if not reparse:
        report(f"using the older parse of {cv.path.name}")
        return _from_cache(cv)
    return _parse_and_cache(cv, llm, report=report, notes_path=notes_path)


def resolved(
    cv: CV, llm: LLM, *, ask: Callable[[str], str] | None = None, **kwargs
) -> tuple[Profile, str]:
    """``ensure_parsed``, plus the answer bank folded in.

    The bank is merged here rather than stored in the cached parse so that
    re-parsing an edited CV never discards what the reader told us, and so the
    cached parse stays a faithful record of the file it came from.
    """
    profile, source = ensure_parsed(cv, llm, **kwargs)
    profile = settle_years(cv, profile, ask=ask, report=kwargs.get("report", lambda _: None))
    extra = [note for note in load_extra(cv) if note not in profile.extra_notes]
    if extra:
        profile.extra_notes.extend(extra)
        source = "\n".join([source, *extra])
    return profile, source
