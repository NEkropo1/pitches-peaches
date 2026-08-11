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

from ..llm import LLM, pdf_block, text_block
from ..models import Profile
from ..prompts import render
from ..state import RunState

Reporter = Callable[[str], None]

TEXT_SUFFIXES = {".md", ".txt", ".markdown", ".rst", ""}


def _cv_content(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Return (content blocks for the API, plain text for quote checking).

    The plain text is what quote verification runs against later. For a PDF we
    do not have it up front, so the profile's own JSON stands in — every quote
    the match stage can produce has to come from what the profile extracted.
    """
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return (
            [pdf_block(path), text_block("The CV is the attached PDF.")],
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
    return [text_block(raw)], raw


def run(
    state: RunState,
    llm: LLM,
    cv_path: str,
    *,
    notes_path: str | None = None,
    report: Reporter = lambda _: None,
) -> Profile:
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
                text_block(
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

    state.write_json("profile.json", profile)
    # The quote-verification source. For a PDF the extracted profile is the only
    # text we have; that is the honest source to check quotes against.
    state.write_text(
        "cv-source.txt",
        plain.strip()
        or json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=False),
    )

    state.record(
        "profile",
        cv=str(path),
        skills=len(profile.skills),
        projects=len(profile.projects),
        inconsistencies=len(profile.inconsistencies),
    )
    return profile
