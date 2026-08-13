"""Every schema the pipeline produces, in one place.

Two rules are enforced here rather than asked for politely in a prompt:

1. A claim about the *company* labelled ``verified`` must carry a source. The
   candidate is going to repeat these facts to a human who knows the truth.
2. A match card must carry all four dimensions. A missing dimension is a
   validation error, not a silent gap.

Neither rule applies to anything the candidate says about themselves. That is
taken as true, always. See ``Match`` for the reasoning.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# --------------------------------------------------------------------------
# Stage 1 — recon
# --------------------------------------------------------------------------

Confidence = Literal["verified", "inferred", "unverified"]


class Claim(BaseModel):
    """One fact about the company, labelled by how well it is established."""

    statement: str
    confidence: Confidence
    source: str | None = None
    why_it_matters: str

    @model_validator(mode="after")
    def _verified_needs_source(self) -> Claim:
        if self.confidence == "verified" and not (self.source or "").strip():
            raise ValueError(
                "a claim marked 'verified' must carry a source (URL or "
                f"'job posting'); got none for: {self.statement[:80]!r}"
            )
        return self


class Requirement(BaseModel):
    """One thing the posting asks for."""

    text: str
    kind: Literal["technology", "experience", "domain", "soft", "logistics"]
    must_have: bool
    evidence: str = Field(description="The line in the posting this came from.")


class Person(BaseModel):
    """Someone the candidate is likely to sit across from."""

    name: str
    role: str | None = None
    background: str | None = None
    what_they_will_probe: str | None = None
    sources: list[str] = Field(default_factory=list)


class Recon(BaseModel):
    company: str
    org_type: Literal["startup", "scaleup", "enterprise", "agency", "unknown"]
    headcount_estimate: str | None = None
    role_title: str
    seniority: Literal[
        "junior", "mid", "senior", "staff", "principal", "lead", "unknown"
    ]
    requirements: list[Requirement]
    claims: list[Claim]
    interviewers: list[Person] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    charitable_read: str
    uncharitable_read: str
    known_process: str | None = Field(
        default=None,
        description="The interview process, when the posting or public sources state it.",
    )

    @model_validator(mode="after")
    def _both_reads_present(self) -> Recon:
        for field in ("charitable_read", "uncharitable_read"):
            if not getattr(self, field, "").strip():
                raise ValueError(f"{field} must be non-empty — both readings are required")
        return self


# --------------------------------------------------------------------------
# Stage 2 — profile
# --------------------------------------------------------------------------


class Skill(BaseModel):
    name: str
    cv_line: str = Field(description="The verbatim CV line this skill was read from.")
    years: str | None = None
    depth: Literal["core", "working", "passing"] = "working"


class ProjectEntry(BaseModel):
    name: str
    role: str | None = None
    duration: str | None = None
    team_size: str | None = None
    stack: list[str] = Field(default_factory=list)
    what_you_did: str
    numbers: list[str] = Field(
        default_factory=list,
        description="Concrete figures stated in the CV — latency, scale, headcount, money.",
    )


class TimelineEntry(BaseModel):
    period: str
    what: str


class Inconsistency(BaseModel):
    """Proofreading, not suspicion.

    Two lines of the CV say different things. Surface it so the candidate picks
    one before the call. Never imply which one is true.
    """

    lines: list[str]
    note: str = Field(
        description="Phrased as a choice to make, e.g. 'these two lines say "
        "different things — pick the one you want to lead with'."
    )


class Achievement(BaseModel):
    """A figure the CV states, kept without pretending to know where it happened.

    Produced by ``profiles.consolidate`` when the same number was attributed to
    more than one project — which means the attribution was guessed. The figure
    is true and worth leading with; the project it is bolted to may not be, and
    the reader is the one who would have to defend it.
    """

    figure: str
    claimed_under: list[str] = Field(
        default_factory=list,
        description="The projects this figure was attributed to. More than one means unresolved.",
    )


class ContactDetail(BaseModel):
    """One way to reach the candidate.

    A list of typed pairs rather than a free-form ``dict[str, str]``: an object
    with arbitrary keys cannot be expressed in a strict JSON schema, so a dict
    here is rejected outright by some providers' structured-output modes.
    """

    kind: str = Field(description="email, phone, linkedin, telegram, github, site")
    value: str


class Profile(BaseModel):
    name: str | None = None
    headline: str | None = None
    location: str | None = None
    contact: list[ContactDetail] = Field(default_factory=list)
    years_total: str | None = None
    years_commercial: str | None = None
    languages: list[str] = Field(default_factory=list)
    education: str | None = None
    skills: list[Skill]
    projects: list[ProjectEntry]
    timeline: list[TimelineEntry] = Field(default_factory=list)
    achievements: list[Achievement] = Field(
        default_factory=list,
        description="Figures whose project attribution could not be trusted. Filled in after parsing, not by the model.",
    )
    inconsistencies: list[Inconsistency] = Field(default_factory=list)
    extra_notes: list[str] = Field(
        default_factory=list,
        description="Answers the candidate typed into the probe loop, or --notes content.",
    )


# --------------------------------------------------------------------------
# Stage 3 — match
# --------------------------------------------------------------------------

DIMENSION_NAMES: tuple[str, ...] = (
    "technical",
    "ownership",
    "delivery",
    "business_context",
)


class Dimension(BaseModel):
    name: Literal["technical", "ownership", "delivery", "business_context"]
    score: int = Field(ge=0, le=100)
    reasoning: str


class FitPoint(BaseModel):
    statement: str
    quote: str = Field(description="Verbatim line from the CV or from a probe answer.")
    claim: str


class Gap(BaseModel):
    """Coverage, not credibility.

    'The posting wants Kafka and your background doesn't include it' — never
    'your Kafka claim looks weak'.
    """

    headline: str
    detail: str


class Probe(BaseModel):
    question: str
    why: str
    about: str | None = Field(
        default=None, description="The requirement or CV line that prompted it."
    )


class ProbeSet(BaseModel):
    """Stage 3a — what to ask, decided before anything has been scored.

    Its own call, and a deliberately small one. Asking "what is missing here"
    needs the posting and the CV; it does not need a finished match card. The
    pipeline used to get these by scoring in full, showing a draft, and then
    scoring again from scratch — which paid for one of the longest generations
    in the run twice and threw the first one away.
    """

    probes: list[Probe] = Field(default_factory=list)


class Match(BaseModel):
    overall: int = Field(ge=0, le=100)
    band: Literal["strong", "possible", "weak"]
    dimensions: list[Dimension]
    fit_points: list[FitPoint]
    gaps: list[Gap]
    prepare: list[str]
    probes: list[Probe] = Field(default_factory=list)
    provisional: bool = False

    @model_validator(mode="after")
    def _all_four_dimensions(self) -> Match:
        seen = [d.name for d in self.dimensions]
        missing = [n for n in DIMENSION_NAMES if n not in seen]
        if missing:
            raise ValueError(f"match is missing dimension(s): {', '.join(missing)}")
        dupes = {n for n in seen if seen.count(n) > 1}
        if dupes:
            raise ValueError(f"match has duplicate dimension(s): {', '.join(sorted(dupes))}")
        return self


class MatchDraft(BaseModel):
    """What the model returns. ``band`` is derived in code, not asked for."""

    overall: int = Field(ge=0, le=100)
    dimensions: list[Dimension]
    fit_points: list[FitPoint]
    gaps: list[Gap]
    prepare: list[str]
    probes: list[Probe] = Field(default_factory=list)

    @model_validator(mode="after")
    def _all_four_dimensions(self) -> MatchDraft:
        seen = [d.name for d in self.dimensions]
        missing = [n for n in DIMENSION_NAMES if n not in seen]
        if missing:
            raise ValueError(f"match is missing dimension(s): {', '.join(missing)}")
        return self


# --------------------------------------------------------------------------
# Stage 4 — gate
# --------------------------------------------------------------------------

Recommendation = Literal["apply", "apply_with_caveats", "do_not_apply"]


class Gate(BaseModel):
    recommendation: Recommendation
    reason: str
    spread_read: str = Field(
        description="What the shape of the four dimension scores means, not just the total."
    )
    strongest: list[str]
    most_damaging: list[str]
    build_first: list[str] = Field(
        default_factory=list,
        description="If the recommendation is do_not_apply: what to build before the next one.",
    )


# --------------------------------------------------------------------------
# Stage 5 — playbook
# --------------------------------------------------------------------------


class Round(BaseModel):
    name: str
    duration: str | None = None
    what_is_assessed: str
    how_to_run_it: str


class DeepDive(BaseModel):
    topic: str
    walkthrough: str = Field(description="Mechanism-level. Long. No bullet walls.")


class Question(BaseModel):
    question: str
    why_this_one: str = Field(
        description="Why a strong senior finds this interesting rather than obvious."
    )
    answer: str = Field(description="Maximally detailed, architectural-interview depth.")
    deep_dives: list[DeepDive] = Field(default_factory=list)


class TechnologyBlock(BaseModel):
    technology: str
    why_it_matters_here: str
    questions: list[Question]


class Playbook(BaseModel):
    branch: Literal["structured", "founder_led"]
    rounds: list[Round] = Field(default_factory=list)
    interviewer_profiles: list[Person] = Field(default_factory=list)
    pitch_adaptation: str | None = Field(
        default=None,
        description="How to adapt the pitch to whoever is actually in the room.",
    )
    technologies: list[TechnologyBlock]
    closing_questions: list[str] = Field(
        default_factory=list,
        description="What the candidate asks them. Due diligence runs both ways.",
    )


# --------------------------------------------------------------------------
# Stage 6 — render
# --------------------------------------------------------------------------


class Diagram(BaseModel):
    name: Literal["architecture", "process"]
    title: str
    mermaid: str = Field(description="Diagram source, starting with 'flowchart TD'. No fence.")


class Diagrams(BaseModel):
    diagrams: list[Diagram]


# --------------------------------------------------------------------------
# Scoring — display banding, kept in one visible, tunable function
# --------------------------------------------------------------------------

BAND_STRONG = 80
BAND_POSSIBLE = 55


def band_for(overall: int) -> Literal["strong", "possible", "weak"]:
    """Derive the display band from the overall score.

    This is banding, not scoring. The number comes from the model; this only
    decides which of three words sits next to it. Thresholds live here so they
    are visible and tunable in exactly one place.
    """
    if overall >= BAND_STRONG:
        return "strong"
    if overall >= BAND_POSSIBLE:
        return "possible"
    return "weak"
