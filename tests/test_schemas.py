"""Schema validators — the two rules that are enforced, not requested."""

import pytest
from pydantic import ValidationError

from pitches_peaches.models import (
    Claim,
    Dimension,
    Gap,
    FitPoint,
    Match,
    MatchDraft,
    Recon,
    Requirement,
)


def _claim(**kw):
    base = dict(
        statement="Raised a $2.2M seed in April 2026.",
        confidence="verified",
        source="https://example.com/funding",
        why_it_matters="It tells you roughly how long the runway is.",
    )
    base.update(kw)
    return Claim(**base)


def test_verified_claim_requires_a_source():
    with pytest.raises(ValidationError) as err:
        _claim(source=None)
    assert "verified" in str(err.value)


def test_verified_claim_rejects_a_blank_source():
    with pytest.raises(ValidationError):
        _claim(source="   ")


def test_inferred_and_unverified_claims_need_no_source():
    assert _claim(confidence="inferred", source=None).source is None
    assert _claim(confidence="unverified", source=None).source is None


def test_job_posting_counts_as_a_source():
    assert _claim(source="job posting").source == "job posting"


def _recon(**kw):
    base = dict(
        company="Example",
        org_type="startup",
        role_title="Founding Engineer",
        seniority="senior",
        requirements=[
            Requirement(
                text="Kafka in production",
                kind="technology",
                must_have=True,
                evidence="You will own our event pipeline (Kafka).",
            )
        ],
        claims=[_claim()],
        charitable_read="Relentless adaptability and a nose for where the market moves.",
        uncharitable_read="They repeatedly find distribution without finding durable PMF.",
    )
    base.update(kw)
    return Recon(**base)


def test_recon_requires_both_readings():
    assert _recon().charitable_read
    with pytest.raises(ValidationError):
        _recon(charitable_read="")
    with pytest.raises(ValidationError):
        _recon(uncharitable_read="   ")


def _dimensions(names=("technical", "ownership", "delivery", "business_context")):
    return [
        Dimension(name=n, score=70, reasoning="You have shipped at this bar.")
        for n in names
    ]


def _match_kwargs(**kw):
    base = dict(
        overall=72,
        band="possible",
        dimensions=_dimensions(),
        fit_points=[
            FitPoint(
                statement="You have run the exact migration they are about to attempt.",
                quote="moved to self-managed Kubernetes",
                claim="Kubernetes platform ownership",
            )
        ],
        gaps=[Gap(headline="No Kafka in production.", detail="The posting wants it.")],
        prepare=["Have one incident story ready with the invariant you added."],
    )
    base.update(kw)
    return base


def test_match_requires_all_four_dimensions():
    Match(**_match_kwargs())
    with pytest.raises(ValidationError) as err:
        Match(**_match_kwargs(dimensions=_dimensions(("technical", "ownership"))))
    assert "delivery" in str(err.value)
    assert "business_context" in str(err.value)


def test_match_rejects_duplicate_dimensions():
    dims = _dimensions() + [
        Dimension(name="technical", score=10, reasoning="second opinion")
    ]
    with pytest.raises(ValidationError) as err:
        Match(**_match_kwargs(dimensions=dims))
    assert "duplicate" in str(err.value)


def test_match_draft_also_requires_all_four():
    with pytest.raises(ValidationError):
        MatchDraft(
            overall=50,
            dimensions=_dimensions(("technical",)),
            fit_points=[],
            gaps=[],
            prepare=[],
        )


def test_dimension_score_is_bounded():
    with pytest.raises(ValidationError):
        Dimension(name="technical", score=101, reasoning="x")
    with pytest.raises(ValidationError):
        Dimension(name="technical", score=-1, reasoning="x")
