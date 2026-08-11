"""Rewrite technical prose for the ear.

The synthesizer is the easy part. The hard part is feeding it text a human
would actually read aloud: raw technical prose is full of glyphs and acronyms
that every engine mangles — "CI/CD" becomes "C-I-slash-C-D", "LLM01" becomes
"llm one", "→" is silently dropped.

The acronym rules and the ``{{pause:N}}`` marker syntax come from voxsmith,
the author's own macOS TTS library, so scripts written for one work in the
other. voxsmith itself is not vendored: it is macOS-only, and this has to run
on Linux and Windows too.
"""

from __future__ import annotations

import re

#: Acronyms a human pronounces as a word. Everything else gets spelled out.
SPEAK_AS_WORD: set[str] = {
    "NIST", "OWASP", "RAG", "SOC", "STRIDE", "ATLAS", "MITRE", "SBOM",
    "SAST", "DAST", "SIEM", "SOAR", "JSON", "YAML", "REST", "CRUD",
    "SAML", "SCIM", "SPIFFE", "EPAM", "SaaS", "GRPC", "ARM", "SQL",
    "AWS", "JIRA", "CUDA", "SLA", "SLO", "MVP", "PMF", "OKR",
}

#: Explicit pronunciations that beat any general rule.
LEXICON: dict[str, str] = {
    "CI/CD": "C I, C D",
    "AI/ML": "A I, M L",
    "I/O": "I O",
    "S3": "S 3",
    "K8s": "Kubernetes",
    "k8s": "Kubernetes",
    "HITL": "human in the loop",
    "e.g.": "for example",
    "i.e.": "that is",
    "etc.": "and so on",
    "vs.": "versus",
    "&": " and ",
    "→": " leads to ",
    "->": " leads to ",
    "=>": " leads to ",
    "≥": " at least ",
    "≤": " at most ",
    "~": " roughly ",
    "%": " percent",
    "…": ". ",
    "—": ", ",
    "–": ", ",
    "“": '"', "”": '"', "‘": "'", "’": "'",
    # product and infra names the ear needs respelled
    "ChatGPT": "Chat G P T",
    "OpenAI": "Open A I",
    "FastAPI": "Fast A P I",
    "PostgreSQL": "Postgres",
    "ZeroMQ": "Zero M Q",
    "OAuth2": "O auth two",
    "OAuth": "O auth",
    "mTLS": "mutual T L S",
    "Nginx": "Engine X",
    "nginx": "Engine X",
    "Pub/Sub": "Pub Sub",
    "GitHub": "Git Hub",
    "GitLab": "Git Lab",
    "PyPI": "pie pee eye",
    # plurals of spelled acronyms, respelled so the plural stays audible
    "APIs": "ay pee eyes",
    "IDs": "eye deez",
    "SDKs": "ess dee kays",
    "ADRs": "architecture decision records",
    "ADR": "architecture decision record",
    "SMBs": "small businesses",
    "SMB": "small business",
}

_ACRONYM_RE = re.compile(r"\b([A-Z]{2,6})(s)?\b")
_CODE_RE = re.compile(r"\b([A-Z]{2,4})(\d{2})(?::(\d{4}))?\b")
_PAUSE_RE = re.compile(r"\{\{\s*pause\s*:\s*(\d{1,5})\s*\}\}", re.I)

_DIGITS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

# Markdown that survives into a narration script despite the prompt asking for
# none. Cheap insurance — a stray asterisk is read aloud as "asterisk".
_MD_PATTERNS = [
    (re.compile(r"^\s{0,3}#{1,6}\s+", re.M), ""),
    (re.compile(r"```[\w-]*\n(.*?)```", re.S), r"\1"),
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"(?<!\w)\*([^*\n]+)\*(?!\w)"), r"\1"),
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
    (re.compile(r"^\s{0,3}[-*+]\s+", re.M), ""),
    (re.compile(r"^\s{0,3}>\s?", re.M), ""),
    (re.compile(r"^\s*\|.*\|\s*$", re.M), ""),
]


def _spell(word: str) -> str:
    return " ".join(word)


def _expand_code(match: re.Match[str]) -> str:
    prefix, digits = match.group(1), match.group(2)
    spoken = prefix if prefix in SPEAK_AS_WORD else _spell(prefix)
    return f"{spoken} " + " ".join(_DIGITS[d] for d in digits)


def _expand_acronym(match: re.Match[str]) -> str:
    word, plural = match.group(1), match.group(2)
    if word in SPEAK_AS_WORD:
        return word + (plural or "")
    return _spell(word) + ("s" if plural else "")


def strip_markdown(text: str) -> str:
    for pattern, replacement in _MD_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def strip_pause_markers(text: str) -> str:
    """Remove pause markers without converting them — for word counts."""
    return _PAUSE_RE.sub(" ", text)


def pause_markers(text: str) -> list[int]:
    return [int(m.group(1)) for m in _PAUSE_RE.finditer(text)]


def normalize_for_speech(text: str, *, pauses: str = "keep") -> str:
    """Rewrite text so a synthesizer reads it correctly.

    ``pauses``: ``keep`` leaves ``{{pause:N}}`` markers in place (a backend
    that understands them handles them), ``strip`` removes them, ``say``
    converts them to the macOS ``[[slnc N]]`` command.
    """
    # Neutralize any literal [[...]] first so input can never smuggle a command
    # into the synthesizer. The input is untrusted; that felt like the right
    # instinct given what this reads.
    text = text.replace("[[", "( ").replace("]]", " )")
    text = strip_markdown(text)

    slots: list[str] = []

    def stash(match: re.Match[str]) -> str:
        slots.append(match.group(1))
        return f"\x00PAUSE{len(slots) - 1}\x00"

    text = _PAUSE_RE.sub(stash, text)

    for source in sorted(LEXICON, key=len, reverse=True):
        text = text.replace(source, LEXICON[source])

    text = _CODE_RE.sub(_expand_code, text)
    text = _ACRONYM_RE.sub(_expand_acronym, text)
    text = re.sub(r"(?<=\w)\s*/\s*(?=\w)", " or ", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" *\n *", "\n", text)

    def restore(match: re.Match[str]) -> str:
        ms = slots[int(match.group(1))]
        if pauses == "say":
            return f"[[slnc {ms}]]"
        if pauses == "strip":
            return " "
        return "{{pause:" + ms + "}}"

    return re.sub(r"\x00PAUSE(\d+)\x00", restore, text).strip()


def estimate_duration(text: str, rate: int = 178) -> float:
    """Estimated seconds of speech at ``rate`` words per minute."""
    words = len(strip_pause_markers(text).split())
    pause_seconds = sum(pause_markers(text)) / 1000
    return words / max(rate, 1) * 60.0 + pause_seconds
