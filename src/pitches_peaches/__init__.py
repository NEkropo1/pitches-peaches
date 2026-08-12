"""PitchesPeaches — a job posting plus your CV, turned into a prep dossier.

It produces files on disk. It never submits an application, opens a browser, or
touches a job board account. That constraint is a product feature.
"""

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# What has actually been run against a live API.
#
# One source of truth, read by the CLI and asserted against the README and the
# skill wrapper in tests, so the three cannot drift apart. Update this only
# when a full `pytest --e2e` has genuinely passed on the combination — not when
# the code merely looks right.
# ---------------------------------------------------------------------------

#: The provider/model the full six-stage pipeline has been verified on.
VERIFIED_PROVIDER = "openai"
VERIFIED_MODEL = "gpt-5.4-mini"

#: Paths that remain unproven even on the verified provider/model.
UNVERIFIED_PATHS = (
    "the Anthropic and Gemini providers",
    "any model other than " + VERIFIED_MODEL,
    "PDF CVs (the live run used a JSON CV)",
    "the interactive probe loop and gate prompt",
    "audio rendering",
)


def verification_notice() -> str:
    """One paragraph, for anywhere a person might be about to trust this."""
    return (
        f"v{__version__} has been verified end to end on "
        f"{VERIFIED_PROVIDER}/{VERIFIED_MODEL} only, non-interactive and "
        "without audio. Everything else is unit tested but has never made a "
        "live call: " + ", ".join(UNVERIFIED_PATHS) + "."
    )


def is_verified(provider: str, model: str) -> bool:
    return provider == VERIFIED_PROVIDER and model == VERIFIED_MODEL
