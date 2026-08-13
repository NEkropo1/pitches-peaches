"""Stage 2 — parse the CV into structured form.

Accepts ``.json`` (the cv.json shape), ``.md``, ``.txt``, and ``.pdf``. A PDF
goes to the model as a document content block; we do not shell out to a PDF
library, because a CV's layout carries meaning that a text extractor drops.

There are no content guardrails on CV text, deliberately. This is open source,
users supply their own CV, and if someone prompt-injects their own dossier the
only person affected is them. The structural answer is that the extraction
schema is closed: an injected instruction has nowhere to land.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..llm import PDF, LLM, Text
from ..models import Profile
from ..prompts import render
from ..state import RunState

Reporter = Callable[[str], None]

TEXT_SUFFIXES = {".md", ".txt", ".markdown", ".rst", ""}


def _cv_content(path: Path) -> tuple[list[Any], str]:
    """Return (content blocks for the API, plain text for quote checking).

    The plain text is what quote verification runs against later. For a PDF we
    do not have it up front, so the profile's own JSON stands in — every quote
    the match stage can produce has to come from what the profile extracted.
    """
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return (
            [PDF(path), Text("The CV is the attached PDF.")],
            "",
        )

    raw = path.read_text(encoding="utf-8")
    if suffix == ".json":
        # Pretty-print so the model reads the same line breaks the reader sees.
        try:
            raw = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pass  # not valid JSON despite the suffix; send it as-is
    elif suffix not in TEXT_SUFFIXES:
        raise ValueError(
            f"cannot read a CV from {path.suffix or 'a file with no extension'}. "
            "Supported: .json, .md, .txt, .pdf"
        )
    return [Text(raw)], raw


def parse_cv(
    llm: LLM,
    cv_path: str | Path,
    *,
    notes_path: str | None = None,
    report: Reporter = lambda _: None,
) -> tuple[Profile, str]:
    """The paid half: one model call, returning the profile and its source text.

    Split out from ``run`` because a CV is parsed once and read by every
    application that uses it. This function knows nothing about where the
    result is stored, which is what lets the same call serve a single run
    directory and a workspace-wide CV cache.

    The second element is the text quote verification runs against. For a PDF
    we have none, so the caller substitutes the extracted profile — see ``run``.
    """
    path = Path(cv_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"no CV at {path}")

    blocks, plain = _cv_content(path)

    extra_notes: list[str] = []
    if notes_path:
        note_text = Path(notes_path).expanduser().read_text(encoding="utf-8").strip()
        if note_text:
            extra_notes.append(note_text)
            blocks.append(
                Text(
                    "\n--- extra context the reader supplied about themselves "
                    "(true, same standing as the CV) ---\n" + note_text
                )
            )
            plain = f"{plain}\n{note_text}"

    report(f"reading {path.name}")
    profile = llm.parse(
        Profile,
        system=render("profile", cv="(supplied in the user message)"),
        content=blocks,
    )
    profile.extra_notes.extend(extra_notes)
    return profile, plain


def source_text(profile: Profile, plain: str) -> str:
    """What quote verification checks against.

    For a PDF the extracted profile is the only text we have; that is the
    honest source to check quotes against, and pretending otherwise would let
    a quote pass because nothing could contradict it.
    """
    return plain.strip() or json.dumps(
        profile.model_dump(mode="json"), indent=2, ensure_ascii=False
    )


def write(state: RunState, profile: Profile, source: str, cv_path: str | Path) -> None:
    """Put an already-parsed CV into a run directory.

    Separate from ``parse_cv`` so a cached parse lands identically to a fresh
    one: every downstream stage reads ``profile.json`` from the run directory
    and never needs to know which of the two it got.
    """
    state.write_json("profile.json", profile)
    state.write_text("cv-source.txt", source)
    state.record(
        "profile",
        cv=str(cv_path),
        skills=len(profile.skills),
        projects=len(profile.projects),
        inconsistencies=len(profile.inconsistencies),
    )


def run(
    state: RunState,
    llm: LLM,
    cv_path: str,
    *,
    notes_path: str | None = None,
    report: Reporter = lambda _: None,
) -> Profile:
    profile, plain = parse_cv(llm, cv_path, notes_path=notes_path, report=report)
    write(state, profile, source_text(profile, plain), cv_path)
    return profile
