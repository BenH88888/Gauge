"""Unit tests for the what-if sweep."""

from __future__ import annotations

import pytest

from gauge.benefits.models import Plan
from gauge.predictor.model import CostPredictor
from gauge.predictor.schemas import PredictionFeatures
from gauge.predictor.whatif import sweep

pytestmark = pytest.mark.unit


def test_sweep_rejects_unknown_feature(
    trained_predictor: CostPredictor,
    baseline_features: PredictionFeatures,
) -> None:
    with pytest.raises(ValueError, match="Cannot sweep 'income'"):
        sweep(
            predictor=trained_predictor,
            baseline=baseline_features,
            feature="income",
            values=[1, 2, 3],
        )


def test_sweep_returns_one_point_per_value(
    trained_predictor: CostPredictor,
    baseline_features: PredictionFeatures,
) -> None:
    values = [25, 35, 45, 55]
    response = sweep(
        predictor=trained_predictor,
        baseline=baseline_features,
        feature="age",
        values=values,
    )
    assert response.feature == "age"
    assert [p.value for p in response.points] == values
    # No plan supplied — OOP interval should be absent.
    assert all(p.oop_interval is None for p in response.points)


def test_sweep_empty_values_returns_empty(
    trained_predictor: CostPredictor,
    baseline_features: PredictionFeatures,
) -> None:
    response = sweep(
        predictor=trained_predictor,
        baseline=baseline_features,
        feature="age",
        values=[],
    )
    assert response.points == []


def test_sweep_charges_increase_with_age(
    trained_predictor: CostPredictor,
    baseline_features: PredictionFeatures,
) -> None:
    response = sweep(
        predictor=trained_predictor,
        baseline=baseline_features,
        feature="age",
        values=[20, 40, 60],
    )
    charges = [p.prediction.median_charges_cents for p in response.points]
    assert charges[0] < charges[2]


def test_sweep_with_plan_returns_oop_interval(
    trained_predictor: CostPredictor,
    baseline_features: PredictionFeatures,
    ppo_gold: Plan,
) -> None:
    """Each point should have a valid OOP interval; smokers cost more OOP."""
    response = sweep(
        predictor=trained_predictor,
        baseline=baseline_features,
        feature="smoker",
        values=["no", "yes"],
        plan=ppo_gold,
    )
    assert len(response.points) == 2
    for point in response.points:
        interval = point.oop_interval
        assert interval is not None
        # Monotonicity: lower ≤ median ≤ upper in OOP space.
        assert interval.lower_cents <= interval.median_cents
        assert interval.median_cents <= interval.upper_cents
        # Width is non-negative.
        assert interval.width_cents >= 0

    non_smoker, smoker = response.points
    # Smokers should have a higher median OOP than non-smokers.
    assert smoker.oop_interval.median_cents >= non_smoker.oop_interval.median_cents  # type: ignore[union-attr]


def test_sweep_invalid_value_for_feature_raises(
    trained_predictor: CostPredictor,
    baseline_features: PredictionFeatures,
) -> None:
    """A string in an age sweep should be rejected with a clear ValueError."""
    with pytest.raises(ValueError, match="Invalid value 'twenty'"):
        sweep(
            predictor=trained_predictor,
            baseline=baseline_features,
            feature="age",
            values=["twenty"],
        )
