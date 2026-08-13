"""Several applications, several CVs, and the boundaries between them.

A job search is not one run. It is a handful of applications, one or two CVs,
and the same company research read again every time you try a different CV
against the same posting. This module is the layout that stops you paying for
the same work twice.

Three things depend on three different inputs, and conflating any two of them
costs either money or correctness:

===========================  ==========================  ====================
Artifact                     Depends on                  Lives
===========================  ==========================  ====================
recon.json, 01-company.md    the posting                 the application
the parsed CV, cv-source     the CV file                 ``cvs/.parsed/``
match, gate, playbook, …     the posting **and** the CV  ``by-cv/<name>/``
===========================  ==========================  ====================

Recon is the most expensive stage in the pipeline — three model requests and
around twenty web searches — and it does not depend on the CV at all. Putting
it above the CV split is the whole point of the layout:

    workspace/
    ├── peaches.toml
    ├── cvs/
    │   ├── backend-senior.pdf          yours, never touched
    │   └── .parsed/                    derived; delete it and it rebuilds
    │       ├── backend-senior.json
    │       └── backend-senior.source.txt
    └── applications/
        ├── .next_id
        └── 01-acme/
            ├── application.json
            ├── recon.json              shared by every CV below
            ├── 01-company.md
            └── by-cv/
                ├── backend-senior/     run.json, match.json, fit.html, …
                └── platform-lead/

Nothing here is a cache of state that could be derived. The board is produced
by scanning the directories, because an index file is one more thing that goes
stale. The only stored scalar is the id counter, which genuinely cannot be
recovered once a directory is deleted.

Naming never costs a model call and never waits for one. The directory name is
a handle, computed from the URL or filename by string work alone; the human
label — company and role — is read from ``recon.json`` when that file happens
to exist, because recon already extracted it and reading it back is free.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

CVS_DIR = "cvs"
APPLICATIONS_DIR = "applications"
PARSED_DIR = ".parsed"
BY_CV_DIR = "by-cv"
COUNTER_FILE = ".next_id"
APPLICATION_FILE = "application.json"

#: Artifacts that depend on the posting alone, so every CV shares one copy.
SHARED_ARTIFACTS = frozenset({"recon.json", "recon-notes.md", "01-company.md"})

CV_SUFFIXES = {".json", ".md", ".txt", ".markdown", ".rst", ".pdf"}

SLUG_MAX = 40

#: A workspace holds your CV and dossiers about jobs you are applying to. Both
#: are personal, and neither belongs in a repository by accident — so the
#: default is to ignore them and let anyone who wants them committed say so.
GITIGNORE_WORKSPACE = """\
.env
cvs/
applications/
*.wav
*.mp3
*.aiff
__pycache__/
"""


# --------------------------------------------------------------------------
# Naming — pure string work, no network, no model, no waiting for one
# --------------------------------------------------------------------------

#: Path segments that are scaffolding on every job board in existence.
_STOPWORDS = frozenset({
    "jobs", "job", "careers", "career", "vacancies", "vacancy", "positions",
    "position", "opening", "openings", "apply", "application", "view", "embed",
    "listing", "listings", "detail", "details", "posting", "postings", "role",
    "roles", "en", "en-us", "en-gb", "us", "uk", "eu", "gb", "de", "ua",
    "j", "o", "p", "d", "c", "s", "jobboard", "job-boards", "board", "boards",
    "companies", "company", "employer", "employers", "org", "orgs", "team",
})

#: Subdomains that name the recruiting product, never the company.
_GENERIC_HOST_LABELS = frozenset({
    "www", "jobs", "job", "careers", "career", "apply", "boards", "job-boards",
    "hire", "hiring", "work", "recruiting", "recruit", "talent", "my", "secure",
    "app", "join", "grnh", "emea",
})

#: Suffixes whose *first* path segment is the company, not the host.
_ATS_HOSTS = (
    "greenhouse.io", "lever.co", "workable.com", "ashbyhq.com",
    "myworkdayjobs.com", "workday.com", "smartrecruiters.com", "breezy.hr",
    "recruitee.com", "teamtailor.com", "jobvite.com", "icims.com", "taleo.net",
    "bamboohr.com", "personio.de", "pinpointhq.com", "join.com", "rippling.com",
    "linkedin.com", "indeed.com", "glassdoor.com", "wellfound.com", "angel.co",
    "otta.com", "welcometothejungle.com", "workatastartup.com", "djinni.co",
    "dou.ua", "hh.ru", "robota.ua", "ycombinator.com",
)

_TLD_LABELS = frozenset({
    "com", "org", "net", "io", "co", "uk", "de", "ua", "ai", "dev", "me",
    "us", "eu", "app", "hr", "ru", "pl", "fr", "es", "it", "nl", "se", "ch",
})

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_HEX = re.compile(r"^[0-9a-f]{8,}$", re.I)


#: Cyrillic transliteration, because dropping it is not an option here.
#:
#: NFKD plus ``encode("ascii", "ignore")`` folds accented Latin correctly and
#: deletes Cyrillic outright — so a posting on DOU, or any company writing its
#: own name, would slug to nothing and land in ``NN-untitled`` alongside every
#: other one. Ukrainian national transliteration, with the Russian-only letters
#: added, is a fixed table and costs nothing.
_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e",
    "є": "ie", "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "i", "й": "i",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ь": "", "ю": "iu", "я": "ia",
    "ё": "e", "ъ": "", "ы": "y", "э": "e",
}


def _transliterate(text: str) -> str:
    return "".join(_CYRILLIC.get(ch, _CYRILLIC.get(ch.lower(), ch)) for ch in text)


def slugify(text: str, max_len: int = SLUG_MAX) -> str:
    """Lowercase ASCII, hyphen-separated, bounded. Never raises."""
    folded = unicodedata.normalize("NFKD", _transliterate(str(text).lower()))
    ascii_only = folded.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    if len(slug) <= max_len:
        return slug
    # Cut on a word boundary when there is one near the limit, so a truncated
    # handle still reads as words rather than a severed syllable.
    cut = slug[:max_len]
    boundary = cut.rfind("-")
    return (cut[:boundary] if boundary > max_len // 2 else cut).strip("-")


def _is_identifier(segment: str) -> bool:
    """True for the opaque ids that job boards put in URLs."""
    if segment.isdigit() or _UUID.match(segment) or _HEX.match(segment):
        return True
    # Workable-style tokens: no word separator, mixed letters and digits.
    return (
        "-" not in segment
        and "_" not in segment
        and len(segment) >= 6
        and any(c.isdigit() for c in segment)
        and any(c.isalpha() for c in segment)
    )


def _trim_trailing_id(segment: str) -> str:
    """``senior-engineer-at-acme-4012345678`` -> ``senior-engineer-at-acme``."""
    parts = segment.split("-")
    while len(parts) > 1 and (parts[-1].isdigit() or _HEX.match(parts[-1])):
        parts.pop()
    return "-".join(parts)


def _company_from_host(host: str) -> str:
    """The company name, when the host belongs to the company rather than an ATS."""
    labels = [lab for lab in host.split(".") if lab not in _GENERIC_HOST_LABELS]
    labels = [lab for lab in labels if lab not in _TLD_LABELS]
    return labels[0] if labels else ""


def _slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.split("@")[-1].split(":")[0].lower()
    segments = [
        unquote(seg) for seg in parsed.path.split("/") if seg and seg.strip(".")
    ]
    kept = [
        _trim_trailing_id(seg)
        for seg in segments
        if seg.lower() not in _STOPWORDS and not _is_identifier(seg)
    ]
    kept = [seg for seg in kept if seg]

    on_ats = any(host == known or host.endswith("." + known) for known in _ATS_HOSTS)
    company = kept[0] if (on_ats and kept) else _company_from_host(host)

    # The job title is almost always the longest multi-word segment.
    titles = [seg for seg in kept if "-" in seg]
    title = max(titles, key=len) if titles else ""

    parts = [part for part in (company, title) if part]
    # A one-segment URL supplies the same string twice; say it once.
    if len(parts) == 2 and (parts[0] == parts[1] or parts[0] in parts[1]):
        parts = [parts[1]]

    return slugify("-".join(parts)) or slugify(host)


def slug_for(target: str) -> str:
    """A directory handle for a posting. Deterministic, offline, always something.

    The fallback chain runs all the way down rather than failing: URL parts,
    then the host, then the filename, then the first twenty characters of
    whatever was passed, then ``untitled``. A bad handle is a cosmetic problem
    and the numeric prefix keeps directories distinct regardless, so there is
    never a reason to stop and ask.
    """
    target = (target or "").strip()
    if not target:
        return "untitled"

    if target.startswith(("http://", "https://")):
        from_url = _slug_from_url(target)
        if from_url:
            return from_url
    else:
        stem = Path(target).expanduser().stem
        if slugify(stem):
            return slugify(stem)

    return slugify(target[:20]) or "untitled"


# --------------------------------------------------------------------------
# The workspace
# --------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Application:
    """One posting, and every CV tried against it."""

    id: int
    path: Path
    handle: str
    target: str = ""
    label: str = ""

    @property
    def by_cv(self) -> Path:
        return self.path / BY_CV_DIR

    def cvs(self) -> list[str]:
        """The CV names this application has been run against, oldest first."""
        if not self.by_cv.is_dir():
            return []
        return sorted(p.name for p in self.by_cv.iterdir() if p.is_dir())

    def run_dir(self, cv: str) -> Path:
        return self.by_cv / cv

    def display(self) -> str:
        """The label when recon has run, the handle until then."""
        return self.label or self.handle


@dataclass(frozen=True)
class CV:
    """One CV file the reader supplied, and its cached parse."""

    name: str
    path: Path
    parsed_dir: Path

    @property
    def parsed_path(self) -> Path:
        return self.parsed_dir / f"{self.name}.json"

    @property
    def source_path(self) -> Path:
        return self.parsed_dir / f"{self.name}.source.txt"

    def digest(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def cached(self) -> dict | None:
        if not self.parsed_path.exists():
            return None
        try:
            return json.loads(self.parsed_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None  # a corrupt cache is a missing cache, not an error

    def state(self) -> str:
        """``unparsed``, ``stale``, or ``ready`` — the only three that matter."""
        cached = self.cached()
        if cached is None:
            return "unparsed"
        return "ready" if cached.get("source_sha256") == self.digest() else "stale"

    def write_cache(self, profile, source_text: str) -> None:
        self.parsed_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": self.name,
            "source": self.path.name,
            "source_sha256": self.digest(),
            "parsed_at": _now(),
            "profile": profile.model_dump(mode="json"),
        }
        self.parsed_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        self.source_path.write_text(source_text, encoding="utf-8")


class WorkspaceError(RuntimeError):
    """The message names the fix, in the style of every other error here."""


@dataclass(frozen=True)
class Workspace:
    """A directory holding ``cvs/`` and ``applications/``."""

    root: Path

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def at(cls, root: Path) -> Workspace:
        return cls(Path(root).expanduser().resolve())

    @classmethod
    def create(cls, root: Path) -> Workspace:
        workspace = cls.at(root)
        workspace.cvs_dir.mkdir(parents=True, exist_ok=True)
        workspace.applications_dir.mkdir(parents=True, exist_ok=True)
        return workspace

    @classmethod
    def discover(cls, start: Path) -> Workspace | None:
        """Walk up from ``start`` looking for a workspace, the way git does.

        This is what lets a stage command work from inside a run directory
        without repeating where the workspace is.
        """
        here = Path(start).expanduser().resolve()
        for candidate in (here, *here.parents):
            if (candidate / CVS_DIR).is_dir() and (candidate / APPLICATIONS_DIR).is_dir():
                return cls(candidate)
        return None

    @property
    def cvs_dir(self) -> Path:
        return self.root / CVS_DIR

    @property
    def applications_dir(self) -> Path:
        return self.root / APPLICATIONS_DIR

    @property
    def parsed_dir(self) -> Path:
        return self.cvs_dir / PARSED_DIR

    # -- CVs ---------------------------------------------------------------

    def cvs(self) -> list[CV]:
        """Every CV file in ``cvs/``, by filename stem, sorted by name."""
        if not self.cvs_dir.is_dir():
            return []
        found: dict[str, CV] = {}
        for path in sorted(self.cvs_dir.iterdir()):
            if path.is_dir() or path.name.startswith("."):
                continue
            if path.suffix.lower() not in CV_SUFFIXES:
                continue
            if path.stem in found:
                raise WorkspaceError(
                    f"two CVs in {self.cvs_dir} are both called {path.stem!r} "
                    f"({found[path.stem].path.name} and {path.name}).\n"
                    "Rename one — the stem is the name this tool uses."
                )
            found[path.stem] = CV(path.stem, path, self.parsed_dir)
        return list(found.values())

    def cv(self, name: str) -> CV:
        for candidate in self.cvs():
            if candidate.name == name:
                return candidate
        known = ", ".join(c.name for c in self.cvs()) or "none yet"
        raise WorkspaceError(
            f"no CV called {name!r} in {self.cvs_dir} (have: {known}).\n"
            "Run: peaches cv add <path to your CV>"
        )

    # -- applications ------------------------------------------------------

    def applications(self) -> list[Application]:
        """Scan for what exists. Derived every time, never cached."""
        if not self.applications_dir.is_dir():
            return []
        found = []
        for path in sorted(self.applications_dir.iterdir()):
            if not path.is_dir() or path.name.startswith("."):
                continue
            number, _, handle = path.name.partition("-")
            if not number.isdigit():
                continue
            found.append(self._load(int(number), path, handle))
        return found

    def application(self, id: int) -> Application:
        for candidate in self.applications():
            if candidate.id == id:
                return candidate
        raise WorkspaceError(
            f"no application {id} in {self.applications_dir}.\nRun: peaches ls"
        )

    def _load(self, id: int, path: Path, handle: str) -> Application:
        data: dict = {}
        record = path / APPLICATION_FILE
        if record.exists():
            try:
                data = json.loads(record.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        return Application(
            id=id,
            path=path,
            handle=handle,
            target=data.get("target", ""),
            label=data.get("label") or self._label_from_recon(path),
        )

    @staticmethod
    def _label_from_recon(path: Path) -> str:
        """Company and role, if recon happens to have run. Never costs a call."""
        recon = path / "recon.json"
        if not recon.exists():
            return ""
        try:
            data = json.loads(recon.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ""
        parts = [data.get("company", ""), data.get("role_title", "")]
        return " · ".join(part for part in parts if part)

    # -- ids ---------------------------------------------------------------

    @property
    def _counter(self) -> Path:
        return self.applications_dir / COUNTER_FILE

    def next_id(self) -> int:
        """The counter, floored by what is on disk.

        Ids are never reused: deleting 02 does not free it, because a path in
        an old ``00-README.md`` or in shell history would then quietly point at
        a different job. The floor is not validation of a hand-edited counter —
        that is the reader's business — it only stops a new application landing
        on an id some existing directory already claims.
        """
        stored = 1
        if self._counter.exists():
            raw = self._counter.read_text(encoding="utf-8").strip()
            if raw.isdigit():
                stored = int(raw)
        highest = max((app.id for app in self.applications()), default=0)
        return max(stored, highest + 1)

    def _bump(self, used: int) -> None:
        self.applications_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._counter.with_suffix(".tmp")
        tmp.write_text(f"{used + 1}\n", encoding="utf-8")
        tmp.replace(self._counter)  # atomic, so an interrupt cannot lose the counter

    def new_application(self, target: str, *, label: str = "") -> Application:
        """Claim the next id and create the directory. No model call."""
        id = self.next_id()
        path = self.applications_dir / f"{id:02d}-{slug_for(target)}"
        path.mkdir(parents=True, exist_ok=True)
        (path / APPLICATION_FILE).write_text(
            json.dumps(
                {"id": id, "target": target, "label": label, "created": _now()},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self._bump(id)
        return self._load(id, path, path.name.partition("-")[2])

    def find_by_target(self, target: str) -> Application | None:
        """An existing application for this posting, so we can offer to resume it."""
        wanted = _normalise_target(target)
        for app in self.applications():
            if app.target and _normalise_target(app.target) == wanted:
                return app
        return None


def _normalise_target(target: str) -> str:
    """Compare postings loosely enough that a trailing slash is not a new job."""
    cleaned = target.strip().rstrip("/")
    if cleaned.startswith(("http://", "https://")):
        parsed = urlparse(cleaned)
        host = parsed.netloc.lower().removeprefix("www.")
        return f"{host}{parsed.path.rstrip('/')}"
    return str(Path(cleaned).expanduser())
