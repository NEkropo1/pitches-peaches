"""Quote verification for the match card.

Every ``FitPoint`` carries a verbatim line from the CV or from a probe answer.
This checks that the line is actually there.

This is a check on *our own output*, not on the candidate. It stops the model
attributing a sentence to someone who never wrote it — which would otherwise
send them into an interview repeating something they cannot back up. It says
nothing about whether the candidate's claims are true; those are taken as true.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-"})


def normalize(text: str) -> str:
    """Collapse whitespace and unify the punctuation that round-trips badly."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_QUOTES).translate(_DASHES)
    return _WS.sub(" ", text).strip().lower()


def quote_appears(quote: str, source: str) -> bool:
    """True when ``quote`` is a substring of ``source`` after normalization."""
    needle = normalize(quote)
    if not needle:
        return False
    return needle in normalize(source)


@dataclass
class QuoteCheck:
    kept: list
    dropped: list
    warnings: list[str]


def filter_fit_points(fit_points, source: str) -> QuoteCheck:
    """Drop fit points whose quote is not in the source, and say which.

    ``fit_points`` is any sequence of objects with ``.quote`` and ``.claim``.
    """
    kept, dropped, warnings = [], [], []
    for point in fit_points:
        if quote_appears(point.quote, source):
            kept.append(point)
        else:
            dropped.append(point)
            warnings.append(
                f'dropped fit point "{point.claim}": its quote does not appear '
                f"in your CV or your answers ({point.quote[:70]!r})"
            )
    return QuoteCheck(kept=kept, dropped=dropped, warnings=warnings)
