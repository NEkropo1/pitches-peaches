"""Stage 1 — research the company, for this application.

Two model calls, deliberately. The first is grounded research with the web
search tool and produces prose notes. The second converts those notes into the
typed record. Splitting them keeps the research free to follow a thread and
keeps the extraction honest — the extractor can only restate what the notes
found, so a fact cannot appear in the schema without appearing in the notes
first.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Callable

from ..llm import LLM
from ..models import Recon
from ..prompts import render
from ..state import RunState

Reporter = Callable[[str], None]


def _read_source(target: str) -> tuple[str, str | None]:
    """Return (posting text, url). ``target`` is a URL or a path to a file."""
    if target.startswith(("http://", "https://")):
        return f"Job posting URL: {target}", target
    path = Path(target).expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"{target} is neither a URL nor a file that exists. Pass the posting "
            "URL, or save the posting to a file and pass its path."
        )
    return path.read_text(encoding="utf-8"), None


def run(
    state: RunState,
    llm: LLM,
    target: str,
    *,
    company: str | None = None,
    posting_file: str | None = None,
    report: Reporter = lambda _: None,
) -> Recon:
    posting, url = _read_source(target)

    if posting_file:
        extra = Path(posting_file).expanduser().read_text(encoding="utf-8")
        posting = f"{posting}\n\n--- pasted posting ---\n{extra}"

    briefing = ["# The job posting", posting]
    if company:
        briefing.append(f"\n# Company name (given by the reader)\n{company}")
    if url:
        briefing.append(
            f"\nFetch and read {url} first — it is the posting itself and the "
            "single most important source. Then research the company."
        )

    report("researching the company")
    research = llm.research(
        system=render("recon_research"),
        content="\n".join(briefing),
        on_search=lambda q: report(f"  search: {q}"),
    )
    state.write_text("recon-notes.md", research.text)

    report("structuring the record")
    recon = llm.parse(
        Recon,
        system=render("recon_extract", notes=research.text),
        content=(
            "Emit the structured recon record from the notes in your system "
            "prompt. The posting itself follows.\n\n"
            f"# The posting\n{posting}"
        ),
    )
    state.write_json("recon.json", recon)

    report("writing 01-company.md")
    document = llm.write(
        system=render(
            "recon_document",
            today=date.today().isoformat(),
            recon=json.dumps(recon.model_dump(mode="json"), indent=2, ensure_ascii=False),
            posting=posting,
        ),
        content=(
            "Write the dossier. The sources actually consulted were:\n"
            + ("\n".join(f"- {s}" for s in research.sources) or "- the job posting only")
        ),
    )
    state.write_text("01-company.md", document)

    state.record(
        "recon",
        target=target,
        url=url,
        company=recon.company,
        claims=len(recon.claims),
        requirements=len(recon.requirements),
        sources=research.sources,
    )
    return recon
