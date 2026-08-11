"""Stage 4 — the decision.

This is the project's ethical spine. A do_not_apply recommendation must be easy
to accept and must exit cleanly with something useful. Do not soften it into an
always-yes.
"""

from __future__ import annotations

import json
from typing import Callable

from ..llm import LLM
from ..models import Gate, Match
from ..prompts import render
from ..state import RunState

Reporter = Callable[[str], None]
Confirm = Callable[[str], bool]

WORDS = {
    "apply": "APPLY",
    "apply_with_caveats": "APPLY, WITH CAVEATS",
    "do_not_apply": "DO NOT APPLY",
}


def summary_lines(gate: Gate, match: Match) -> list[str]:
    from ..cards import DIMENSION_LABELS, _bar, _ordered  # noqa: PLC2701

    out = [
        f"  OVERALL  {match.overall:>3}/100   {match.band.upper()}",
        f"           {_bar(match.overall, 46)}",
        "",
    ]
    for dim in _ordered(match):
        out.append(f"  {DIMENSION_LABELS[dim.name]:<17}{dim.score:>3}  {_bar(dim.score)}")
    out += ["", "  " + gate.spread_read, ""]

    out += ["STRONGEST", ""]
    out += [f"  + {item}" for item in gate.strongest[:3]]
    out += ["", "MOST DAMAGING", ""]
    out += [f"  - {item}" for item in gate.most_damaging[:3]]
    out += ["", f"RECOMMENDATION — {WORDS[gate.recommendation]}", "", "  " + gate.reason]
    if gate.build_first:
        out += ["", "IF YOU SKIP THIS ONE, BUILD FIRST", ""]
        out += [f"  - {item}" for item in gate.build_first]
    return out


def run(
    state: RunState,
    llm: LLM,
    *,
    interactive: bool = True,
    assume: str | None = None,
    report: Reporter = lambda _: None,
    confirm: Confirm | None = None,
) -> tuple[Gate, str]:
    state.require("match.json", "recon.json")
    match = Match.model_validate(state.read_json("match.json"))
    recon = state.read_json("recon.json")

    report("weighing it up")
    gate = llm.parse(
        Gate,
        system=render(
            "gate",
            match=json.dumps(match.model_dump(mode="json"), indent=2, ensure_ascii=False),
            recon=json.dumps(recon, indent=2, ensure_ascii=False),
        ),
        content="Make the recommendation.",
        effort=llm.config.effort,
    )
    state.write_json("gate.json", gate)

    report("")
    for line in summary_lines(gate, match):
        report(line)
    report("")

    if assume in {"proceed", "declined"}:
        decision = assume
    elif not interactive or confirm is None:
        # Non-interactive runs follow the recommendation rather than assuming yes.
        decision = "declined" if gate.recommendation == "do_not_apply" else "proceed"
        report(f"non-interactive: taking the recommendation ({decision})")
    else:
        decision = "proceed" if confirm("Build the playbook for this one?") else "declined"

    state.record_decision(decision, gate.recommendation)
    state.record("gate", recommendation=gate.recommendation, decision=decision)

    if decision != "proceed":
        report("")
        report("Stopping here. Nothing was sent anywhere.")
        if gate.build_first:
            report("")
            report("Here's what to build first:")
            for item in gate.build_first:
                report(f"  - {item}")
    return gate, decision
