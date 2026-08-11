"""Quote verification and score banding."""

from types import SimpleNamespace

import pytest

from pitches_peaches.models import BAND_POSSIBLE, BAND_STRONG, band_for
from pitches_peaches.quotes import filter_fit_points, normalize, quote_appears

CV = """\
Led the migration from a GCP MVP to self-managed Kubernetes, cutting internal
API communication times by 90%.
Redesigned a synchronous pipeline into async parallel workers — end-to-end
processing went from ~3 minutes to ~3 seconds against a 1-minute SLA.
"""


def test_exact_substring_matches():
    assert quote_appears("self-managed Kubernetes", CV)


def test_whitespace_and_newlines_are_normalized():
    assert quote_appears("cutting internal API communication times by 90%", CV)
    assert quote_appears("async parallel   workers", CV)


def test_case_is_ignored():
    assert quote_appears("SELF-MANAGED KUBERNETES", CV)


def test_smart_punctuation_round_trips():
    assert quote_appears("workers — end-to-end", CV)
    assert quote_appears("workers - end-to-end", CV)
    assert quote_appears("workers – end-to-end", CV)


def test_a_line_that_is_not_there_fails():
    assert not quote_appears("owned a Kafka cluster in production", CV)


def test_empty_quote_fails():
    assert not quote_appears("", CV)
    assert not quote_appears("   ", CV)


def test_normalize_collapses_runs_of_whitespace():
    assert normalize("a  \n\t b") == "a b"


def _point(quote, claim="claim"):
    return SimpleNamespace(quote=quote, claim=claim)


def test_filter_keeps_real_quotes_and_drops_invented_ones():
    result = filter_fit_points(
        [
            _point("self-managed Kubernetes", "k8s ownership"),
            _point("I personally invented Kafka", "kafka"),
        ],
        CV,
    )
    assert [p.claim for p in result.kept] == ["k8s ownership"]
    assert [p.claim for p in result.dropped] == ["kafka"]
    assert result.warnings and "kafka" in result.warnings[0]


def test_probe_answers_count_as_source():
    source = CV + "\nProbe: have you used Kafka? -> Yes, three topics in production."
    assert quote_appears("three topics in production", source)


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, "strong"),
        (BAND_STRONG, "strong"),
        (BAND_STRONG - 1, "possible"),
        (70, "possible"),
        (BAND_POSSIBLE, "possible"),
        (BAND_POSSIBLE - 1, "weak"),
        (0, "weak"),
    ],
)
def test_band_thresholds(score, expected):
    assert band_for(score) == expected
