"""PitchesPeaches — a job posting plus your CV, turned into a prep dossier.

It produces files on disk. It never submits an application, opens a browser, or
touches a job board account. That constraint is a product feature.
"""

#: The single source of truth for the version. pyproject.toml reads this
#: attribute, so there is nowhere for the two to disagree.
__version__ = "0.1.2"

# ---------------------------------------------------------------------------
# What has actually been run against a live API.
#
# One source of truth, read by the CLI and asserted against the README, the
# skill wrapper and METRICS.md in tests, so they cannot drift apart. Update
# these only when a run has genuinely happened — not when the code looks right.
#
# Keeping verified and unverified as two explicit lists, rather than one list
# and some prose, is deliberate: the first version of this drifted within a day
# because the prose said "non-interactive" while the measured run had six typed
# probe answers in it.
# ---------------------------------------------------------------------------

#: The provider/model the full six-stage pipeline has been verified on.
VERIFIED_PROVIDER = "openai"
VERIFIED_MODEL = "gpt-5.4-mini"

#: Paths that have been driven end to end on the verified provider/model.
VERIFIED_PATHS = (
    "the full six-stage pipeline, non-interactive",
    "the interactive probe loop and gate prompt",
    "JSON CVs",
    "the workspace: one application, one CV, with the CV parsed into the cache",
    "narration scripts, and audio synthesized with kokoro",
    "a second CV against one posting, reusing the shared recon",
    "parsing a PDF CV into a profile",
)

#: Paths that remain unproven even on the verified provider/model.
UNVERIFIED_PATHS = (
    "the Anthropic and Gemini providers",
    "any model other than " + VERIFIED_MODEL,
    "a complete run on a PDF CV (only the parse has been watched)",
    "the macOS say backend",
)


def verification_notice() -> str:
    """One paragraph, for anywhere a person might be about to trust this."""
    return (
        f"v{__version__} has been verified end to end on "
        f"{VERIFIED_PROVIDER}/{VERIFIED_MODEL} only, covering "
        + ", ".join(VERIFIED_PATHS)
        + ". Everything else is unit tested but has never made a live call: "
        + ", ".join(UNVERIFIED_PATHS)
        + "."
    )


def is_verified(provider: str, model: str) -> bool:
    return provider == VERIFIED_PROVIDER and model == VERIFIED_MODEL
