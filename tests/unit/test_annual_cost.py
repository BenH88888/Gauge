"""Unit tests for the annual cost bridge and OOP interval propagation."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from gauge.benefits.models import Plan
from gauge.predictor.annual_cost import (
    apply_plan_to_annual_spend,
    oop_interval_from_prediction,
)
from gauge.predictor.model import CostPrediction

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# apply_plan_to_annual_spend
# ---------------------------------------------------------------------------


def test_charges_below_deductible_all_on_member(ppo_gold: Plan) -> None:
    share = apply_plan_to_annual_spend(ppo_gold, charges_cents=50_000)
    assert share.deductible_applied_cents == 50_000
    assert share.coinsurance_cents == 0
    assert share.member_pays_cents == 50_000
    assert share.plan_pays_cents == 0
    assert share.capped_at_oop_max is False


def test_charges_above_deductible_split_coinsurance(ppo_gold: Plan) -> None:
    # $1,000 deductible + ($5,000 - $1,000) * 0.20 = $1,800 member share.
    share = apply_plan_to_annual_spend(ppo_gold, charges_cents=500_000)
    assert share.deductible_applied_cents == 100_000
    assert share.coinsurance_cents == 80_000
    assert share.member_pays_cents == 180_000
    assert share.plan_pays_cents == 320_000


def test_oop_max_caps_member_share(ppo_gold: Plan) -> None:
    # Without cap: 100_000 + 0.20 * (5_000_000 - 100_000) = 1_080_000.
    # OOP max is 500_000 so member is capped there.
    share = apply_plan_to_annual_spend(ppo_gold, charges_cents=5_000_000)
    assert share.member_pays_cents == 500_000
    assert share.plan_pays_cents == 4_500_000
    assert share.capped_at_oop_max is True


def test_zero_charges(ppo_gold: Plan) -> None:
    share = apply_plan_to_annual_spend(ppo_gold, charges_cents=0)
    assert share.member_pays_cents == 0
    assert share.plan_pays_cents == 0
    assert share.capped_at_oop_max is False


def test_negative_charges_rejected(ppo_gold: Plan) -> None:
    with pytest.raises(ValueError):
        apply_plan_to_annual_spend(ppo_gold, charges_cents=-1)


def test_components_sum_to_charges(hdhp_silver: Plan) -> None:
    share = apply_plan_to_annual_spend(hdhp_silver, charges_cents=1_234_567)
    assert share.member_pays_cents + share.plan_pays_cents == 1_234_567


def test_apply_plan_monotone(ppo_gold: Plan) -> None:
    """OOP is non-decreasing in charges — the monotonicity property underpinning OopInterval."""
    charge_values = [0, 50_000, 100_000, 200_000, 500_000, 1_000_000, 5_000_000]
    oop_values = [apply_plan_to_annual_spend(ppo_gold, c).member_pays_cents for c in charge_values]
    for a, b in itertools.pairwise(oop_values):
        assert b >= a


# ---------------------------------------------------------------------------
# oop_interval_from_prediction
# ---------------------------------------------------------------------------


def _make_prediction(
    lower_cents: int,
    median_cents: int,
    mean_cents: int,
    upper_cents: int,
    calibrated: bool = True,
) -> CostPrediction:
    """Build a CostPrediction fixture without running the full model stack."""
    return CostPrediction(
        lower_bound_cents=lower_cents,
        median_charges_cents=median_cents,
        mean_charges_cents=mean_cents,
        upper_bound_cents=upper_cents,
        conformal_calibrated=calibrated,
        calibration_coverage=0.80 if calibrated else None,
    )


def test_oop_interval_monotonicity(ppo_gold: Plan) -> None:
    """OOP interval bounds satisfy lower ≤ median ≤ upper."""
    pred = _make_prediction(200_000, 500_000, 600_000, 1_500_000)
    interval = oop_interval_from_prediction(ppo_gold, pred)
    assert interval.lower_cents <= interval.median_cents
    assert interval.median_cents <= interval.upper_cents
    assert interval.width_cents >= 0


def test_oop_interval_inherits_coverage(ppo_gold: Plan) -> None:
    pred = _make_prediction(100_000, 300_000, 350_000, 800_000, calibrated=True)
    interval = oop_interval_from_prediction(ppo_gold, pred)
    assert interval.coverage == 0.80


def test_oop_interval_no_coverage_when_uncalibrated(ppo_gold: Plan) -> None:
    pred = _make_prediction(100_000, 300_000, 350_000, 800_000, calibrated=False)
    interval = oop_interval_from_prediction(ppo_gold, pred)
    assert interval.coverage is None


def test_oop_interval_upper_capped_flag(ppo_gold: Plan) -> None:
    """Upper bound should trigger the cap flag when charges far exceed OOP max."""
    pred = _make_prediction(50_000, 200_000, 250_000, 10_000_000)
    interval = oop_interval_from_prediction(ppo_gold, pred)
    assert interval.capped_at_oop_max_upper is True
    assert not interval.capped_at_oop_max_lower


def test_oop_interval_upper_bounded_by_plan_oop_max(ppo_gold: Plan) -> None:
    """Regardless of charge upper bound, OOP cannot exceed the plan cap."""
    pred = _make_prediction(0, 100_000, 150_000, 100_000_000)
    interval = oop_interval_from_prediction(ppo_gold, pred)
    assert interval.upper_cents == ppo_gold.out_of_pocket_max_cents


def test_oop_interval_zero_charges(ppo_gold: Plan) -> None:
    pred = _make_prediction(0, 0, 0, 0)
    interval = oop_interval_from_prediction(ppo_gold, pred)
    assert interval.lower_cents == 0
    assert interval.median_cents == 0
    assert interval.upper_cents == 0
    assert interval.width_cents == 0


def test_oop_width_cents_property(ppo_gold: Plan) -> None:
    pred = _make_prediction(100_000, 300_000, 350_000, 800_000)
    interval = oop_interval_from_prediction(ppo_gold, pred)
    assert interval.width_cents == interval.upper_cents - interval.lower_cents


def test_oop_interval_empirical_coverage(ppo_gold: Plan) -> None:
    """Monotonicity proof by random sampling.

    For any triple lo ≤ true ≤ hi, OOP(true) must lie in [OOP(lo), OOP(hi)].
    This is the invariant that makes OopInterval a valid uncertainty
    representation when the source CQR interval covers the true charges.
    """
    rng = np.random.default_rng(42)
    lo_charges = rng.integers(0, 500_000, size=500)
    widths = rng.integers(0, 2_000_000, size=500)
    hi_charges = lo_charges + widths
    true_charges = lo_charges + rng.integers(0, widths + 1, size=500)

    for lo, hi, true in zip(lo_charges, hi_charges, true_charges, strict=True):
        oop_lo = apply_plan_to_annual_spend(ppo_gold, int(lo)).member_pays_cents
        oop_hi = apply_plan_to_annual_spend(ppo_gold, int(hi)).member_pays_cents
        oop_true = apply_plan_to_annual_spend(ppo_gold, int(true)).member_pays_cents
        assert oop_lo <= oop_true <= oop_hi
