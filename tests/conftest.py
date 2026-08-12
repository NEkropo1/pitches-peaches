"""Opt-in gating for the tests that make real API calls.

Everything in the default suite is deterministic and offline. The e2e tests
spend real money, so they are skipped unless you ask for them:

    pytest                                # offline suite only
    pytest --e2e                          # everything, live, on Anthropic
    pytest --e2e -k smoke                 # just the cheap live check
    pytest --e2e --provider openai        # the same suite against OpenAI
    pytest --e2e --provider gemini
    PEACHES_E2E=1 pytest                  # same as --e2e, for CI config

The provider is also read from PEACHES_PROVIDER, so a .env with
PEACHES_PROVIDER=openai plus OPENAI_API_KEY needs no flags at all.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def repo_only(*paths: str) -> None:
    """Skip a check whose subject only exists in a source checkout.

    The sdist carries the suite so it can prove itself, but not the whole
    repository — CI config, for one. A test that reads such a file has nothing
    to assert there, and it is the tarball that is incomplete, not the code.
    """
    missing = [path for path in paths if not (REPO_ROOT / path).exists()]
    if missing:
        pytest.skip(f"not a source checkout: {', '.join(missing)} is absent")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests that call a provider API and cost money.",
    )
    parser.addoption(
        "--provider",
        action="store",
        default=None,
        help="Which provider the e2e tests use: anthropic|openai|gemini|auto.",
    )
    parser.addoption(
        "--e2e-model",
        action="store",
        default=None,
        help="Override the model for the e2e tests (default: the provider's).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "e2e: makes real Anthropic API calls; costs money; opt in with --e2e"
    )


def _enabled(config: pytest.Config) -> bool:
    return bool(config.getoption("--e2e")) or os.environ.get("PEACHES_E2E") in {
        "1",
        "true",
        "yes",
    }


def e2e_provider(config: pytest.Config) -> str:
    return (
        config.getoption("--provider")
        or os.environ.get("PEACHES_PROVIDER")
        or "anthropic"
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if _enabled(config):
        from pitches_peaches.providers import select

        name = e2e_provider(config)
        try:
            provider = select(name)
            ok, key = provider.available(), provider.env_key
        except Exception as exc:
            ok, key = False, str(exc)
        if not ok:
            skip = pytest.mark.skip(
                reason=f"--e2e --provider {name} given but {key} is not set"
            )
            for item in items:
                if "e2e" in item.keywords:
                    item.add_marker(skip)
        return

    skip = pytest.mark.skip(reason="needs --e2e (makes real API calls and costs money)")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)
