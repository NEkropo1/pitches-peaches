"""Opt-in gating for the tests that make real API calls.

Everything in the default suite is deterministic and offline. The e2e tests
spend real money, so they are skipped unless you ask for them:

    pytest                  # offline suite only
    pytest --e2e            # everything, including live API calls
    pytest --e2e -k smoke   # just the cheap live check
    PEACHES_E2E=1 pytest    # same as --e2e, for CI environment config
"""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests that call the Anthropic API and cost money.",
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


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if _enabled(config):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            skip = pytest.mark.skip(
                reason="--e2e given but ANTHROPIC_API_KEY is not set"
            )
            for item in items:
                if "e2e" in item.keywords:
                    item.add_marker(skip)
        return

    skip = pytest.mark.skip(reason="needs --e2e (makes real API calls and costs money)")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)
