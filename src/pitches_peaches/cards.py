"""The match card, in three surfaces: terminal, markdown, and standalone HTML.

All three render the same ``Match`` object. No model call happens here — if the
markdown and the HTML ever disagree, that is a bug in this file, not a
difference of opinion between two prompts.
"""

from __future__ import annotations

import html
from typing import Iterable

from .models import Match

BANNER = (
    "AI recommendation — you decide next. PitchesPeaches does not apply to "
    "anything, contact anyone, or send anything anywhere. Everything below is "
    "built from what you provided about yourself."
)

DIMENSION_LABELS = {
    "technical": "TECHNICAL",
    "ownership": "OWNERSHIP",
    "delivery": "DELIVERY",
    "business_context": "BUSINESS CONTEXT",
}

DIMENSION_BLURBS = {
    "technical": "does your stack line up with what they need",
    "ownership": "does your scope match the level they are hiring",
    "delivery": "have you shipped at this cadence and scale",
    "business_context": "do you understand their market and constraints",
}

BAND_WORDS = {"strong": "STRONG FIT", "possible": "POSSIBLE FIT", "weak": "WEAK FIT"}


def _bar(score: int, width: int = 32, filled: str = "█", empty: str = "░") -> str:
    cells = round(score / 100 * width)
    return filled * cells + empty * (width - cells)


def _ordered(match: Match):
    order = list(DIMENSION_LABELS)
    return sorted(match.dimensions, key=lambda d: order.index(d.name))


# -- terminal ----------------------------------------------------------------


def terminal_lines(match: Match, *, role: str = "", company: str = "") -> list[str]:
    """The card as plain lines. Rich styling is applied by the caller."""
    out: list[str] = []
    head = " — ".join(p for p in (role, company) if p)
    if head:
        out += [head, ""]
    out.append(BANNER)
    out.append("")

    label = BAND_WORDS[match.band]
    if match.provisional:
        label += "  (provisional — probes skipped)"
    out.append(f"  OVERALL  {match.overall:>3}/100   {label}")
    out.append(f"           {_bar(match.overall, 46)}")
    out.append("")

    for dim in _ordered(match):
        out.append(f"  {DIMENSION_LABELS[dim.name]:<17}{dim.score:>3}  {_bar(dim.score)}")
        out.append(f"  {'':<17}     {dim.reasoning}")
        out.append("")

    out.append("WHY YOU FIT — WITH EVIDENCE")
    out.append("")
    for point in match.fit_points:
        out.append(f"  {point.statement}")
        for line in _wrap_quote(point.quote):
            out.append(f"      {line}")
        out.append(f"      claim: {point.claim}")
        out.append("")

    out.append("GAPS")
    out.append("")
    for gap in match.gaps:
        out.append(f"  {gap.headline}")
        out.append(f"      {gap.detail}")
        out.append("")

    out.append("WHAT TO PREPARE")
    out.append("")
    for item in match.prepare:
        out.append(f"  - {item}")
    return out


def _wrap_quote(quote: str, width: int = 78) -> list[str]:
    import textwrap

    wrapped = textwrap.wrap(f'"{quote}"', width=width) or ['""']
    return wrapped


# -- markdown ----------------------------------------------------------------


def markdown(match: Match, *, role: str = "", company: str = "") -> str:
    head = " — ".join(p for p in (role, company) if p) or "Fit"
    lines = [f"# Fit: {head}", "", f"> {BANNER}", ""]

    label = BAND_WORDS[match.band]
    if match.provisional:
        label += " *(provisional — the probe loop was skipped)*"
    lines += [
        f"## Overall — {match.overall}/100 · {label}",
        "",
        f"`{_bar(match.overall, 46)}`",
        "",
        "| Dimension | Score | |",
        "|---|---:|---|",
    ]
    for dim in _ordered(match):
        lines.append(
            f"| **{DIMENSION_LABELS[dim.name].title()}** | {dim.score} "
            f"| `{_bar(dim.score, 24)}` |"
        )
    lines.append("")
    for dim in _ordered(match):
        lines.append(f"**{DIMENSION_LABELS[dim.name].title()}** — {dim.reasoning}")
        lines.append("")

    lines += ["## Why you fit — with evidence", ""]
    for point in match.fit_points:
        lines += [
            point.statement,
            "",
            f"> {point.quote}",
            "",
            f"*claim: {point.claim}*",
            "",
        ]

    lines += ["## Gaps", ""]
    for gap in match.gaps:
        lines += [f"**{gap.headline}** {gap.detail}", ""]

    lines += ["## What to prepare", ""]
    lines += [f"- {item}" for item in match.prepare]

    if match.probes:
        lines += ["", "## Still open", ""]
        lines += [f"- {probe.question}" for probe in match.probes]

    return "\n".join(lines).rstrip() + "\n"


# -- HTML --------------------------------------------------------------------

CSS = """\
:root {
  --bg: #0e1012;
  --panel: #16191d;
  --line: #23282e;
  --ink: #e7e9ec;
  --dim: #8b939c;
  --accent: #d8894a;
  --strong: #62b585;
  --possible: #d8b04a;
  --weak: #cf6a5c;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 3rem 1.25rem 5rem;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.65 ui-sans-serif, -apple-system, "Segoe UI", Inter, system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 860px; margin: 0 auto; }
h1 { font-size: 1.5rem; letter-spacing: -0.01em; margin: 0 0 .35rem; font-weight: 600; }
h2 {
  font-size: .78rem; letter-spacing: .14em; text-transform: uppercase;
  color: var(--dim); font-weight: 600; margin: 3rem 0 1.1rem;
  padding-bottom: .5rem; border-bottom: 1px solid var(--line);
}
.banner {
  border: 1px solid var(--line); border-left: 3px solid var(--accent);
  background: var(--panel); border-radius: 4px;
  padding: .85rem 1.1rem; margin: 1.5rem 0 2.5rem;
  color: var(--dim); font-size: .875rem;
}
.overall { display: flex; align-items: baseline; gap: 1rem; flex-wrap: wrap; }
.overall .num { font-size: 3.4rem; font-weight: 600; line-height: 1; letter-spacing: -.03em; }
.overall .of { color: var(--dim); font-size: 1rem; }
.band {
  font-size: .72rem; letter-spacing: .12em; text-transform: uppercase;
  padding: .3rem .7rem; border-radius: 999px; border: 1px solid currentColor;
}
.band.strong { color: var(--strong); }
.band.possible { color: var(--possible); }
.band.weak { color: var(--weak); }
.provisional { color: var(--dim); font-size: .8rem; }
.track { height: 8px; border-radius: 999px; background: var(--line); overflow: hidden; margin: 1rem 0 0; }
.track > i { display: block; height: 100%; background: var(--accent); border-radius: 999px; }
.dim-row { margin: 1.6rem 0; }
.dim-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
.dim-name { font-size: .78rem; letter-spacing: .1em; text-transform: uppercase; font-weight: 600; }
.dim-blurb { color: var(--dim); font-weight: 400; letter-spacing: 0; text-transform: none; font-size: .85rem; }
.dim-score { font-variant-numeric: tabular-nums; font-weight: 600; }
.dim-row .track { height: 6px; margin: .55rem 0 .5rem; }
.dim-why { color: var(--dim); font-size: .9rem; }
.fit { margin: 0 0 1.9rem; }
.fit .statement { margin: 0 0 .7rem; }
.fit blockquote {
  margin: 0 0 .5rem; padding: .55rem 0 .55rem 1.1rem;
  border-left: 2px solid var(--accent); color: var(--ink); font-style: italic;
}
.fit .claim { color: var(--dim); font-size: .78rem; letter-spacing: .06em; text-transform: uppercase; }
.gap { margin: 0 0 1.3rem; }
.gap b { color: var(--weak); }
ul { padding-left: 1.15rem; margin: 0; }
li { margin: 0 0 .55rem; }
footer { margin-top: 4rem; color: var(--dim); font-size: .8rem; border-top: 1px solid var(--line); padding-top: 1rem; }
@media (max-width: 600px) { body { padding: 2rem 1rem 3rem; } .overall .num { font-size: 2.6rem; } }
"""


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _track(score: int) -> str:
    return f'<div class="track"><i style="width:{score}%"></i></div>'


def html_card(match: Match, *, role: str = "", company: str = "") -> str:
    head = " — ".join(p for p in (role, company) if p) or "Fit"
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Fit — {_esc(head)}</title>",
        f"<style>{CSS}</style></head><body><div class=\"wrap\">",
        f"<h1>{_esc(head)}</h1>",
        f'<div class="banner">{_esc(BANNER)}</div>',
        '<div class="overall">',
        f'<span class="num">{match.overall}</span><span class="of">/100</span>',
        f'<span class="band {match.band}">{BAND_WORDS[match.band]}</span>',
    ]
    if match.provisional:
        parts.append(
            '<span class="provisional">provisional — the probe loop was skipped</span>'
        )
    parts += ["</div>", _track(match.overall)]

    parts.append("<h2>Dimensions</h2>")
    for dim in _ordered(match):
        parts += [
            '<div class="dim-row"><div class="dim-head">',
            f'<span class="dim-name">{DIMENSION_LABELS[dim.name]} '
            f'<span class="dim-blurb">— {_esc(DIMENSION_BLURBS[dim.name])}</span></span>',
            f'<span class="dim-score">{dim.score}</span></div>',
            _track(dim.score),
            f'<div class="dim-why">{_esc(dim.reasoning)}</div></div>',
        ]

    parts.append("<h2>Why you fit — with evidence</h2>")
    for point in match.fit_points:
        parts += [
            '<div class="fit">',
            f'<p class="statement">{_esc(point.statement)}</p>',
            f"<blockquote>{_esc(point.quote)}</blockquote>",
            f'<div class="claim">claim: {_esc(point.claim)}</div></div>',
        ]

    parts.append("<h2>Gaps</h2>")
    for gap in match.gaps:
        parts.append(
            f'<p class="gap"><b>{_esc(gap.headline)}</b> {_esc(gap.detail)}</p>'
        )

    parts.append("<h2>What to prepare</h2><ul>")
    parts += [f"<li>{_esc(item)}</li>" for item in match.prepare]
    parts.append("</ul>")

    if match.probes:
        parts.append("<h2>Still open</h2><ul>")
        parts += [f"<li>{_esc(p.question)}</li>" for p in match.probes]
        parts.append("</ul>")

    parts.append(
        "<footer>Generated locally by PitchesPeaches. Nothing was sent anywhere "
        "but the Anthropic API, under your own key.</footer>"
    )
    parts.append("</div></body></html>")
    return "\n".join(parts) + "\n"


def mermaid_block(source: str) -> str:
    return "```mermaid\n" + source.strip() + "\n```"


def join(lines: Iterable[str]) -> str:
    return "\n".join(lines)
