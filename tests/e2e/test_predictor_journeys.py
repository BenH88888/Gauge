"""End-to-end predictor journeys.

These chain ``/predict`` and ``/whatif`` calls into the kind of session a
real client would run: predict a baseline, compare quitting smoking,
sweep age, layer in a plan to see the annual OOP interval.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gauge.api import create_app
from gauge.benefits.seed import build_default_repository
from gauge.predictor.model import CostPredictor

pytestmark = pytest.mark.e2e


@pytest.fixture
def client(trained_predictor: CostPredictor) -> TestClient:
    return TestClient(
        create_app(build_default_repository(), trained_predictor)
    )


def _baseline_payload() -> dict:
    return {
        "age": 40,
        "sex": "male",
        "bmi": 32.0,
        "children": 2,
        "smoker": "yes",
        "region": "south",
    }


def test_journey_quit_smoking_lowers_predicted_cost(
    client: TestClient,
) -> None:
    smoker = client.post(
        "/predict", json={"features": _baseline_payload()}
    ).json()
    nonsmoker = client.post(
        "/predict",
        json={"features": _baseline_payload() | {"smoker": "no"}},
    ).json()
    assert (
        nonsmoker["prediction"]["median_charges_cents"]
        < smoker["prediction"]["median_charges_cents"]
    )


def test_journey_age_sweep_under_a_plan(client: TestClient) -> None:
    """Sweep age; charges and OOP interval should both trend up at the endpoints."""
    response = client.post(
        "/whatif",
        json={
            "baseline": _baseline_payload() | {"smoker": "no"},
            "feature": "age",
            "values": [25, 35, 45, 55, 64],
            "plan_id": "ppo_gold",
        },
    ).json()
    points = response["points"]
    assert len(points) == 5

    charges = [p["prediction"]["median_charges_cents"] for p in points]
    assert charges[-1] > charges[0]

    # Every point has a valid, monotone OOP interval.
    for p in points:
        interval = p["oop_interval"]
        assert interval is not None
        assert interval["lower_cents"] <= interval["median_cents"]
        assert interval["median_cents"] <= interval["upper_cents"]


def test_journey_predict_then_apply_plan_has_oop_interval(
    client: TestClient,
) -> None:
    """Requesting /predict with a plan_id yields a well-formed OOP interval."""
    without_plan = client.post(
        "/predict", json={"features": _baseline_payload()}
    ).json()
    with_plan = client.post(
        "/predict",
        json={"features": _baseline_payload(), "plan_id": "hdhp_silver"},
    ).json()

    # Prediction is the same with or without a plan.
    assert (
        with_plan["prediction"]["median_charges_cents"]
        == without_plan["prediction"]["median_charges_cents"]
    )
    # OOP interval is present only when a plan is supplied.
    assert without_plan["oop_interval"] is None
    interval = with_plan["oop_interval"]
    assert interval is not None
    assert interval["lower_cents"] <= interval["median_cents"] <= interval["upper_cents"]
    assert interval["coverage"] == pytest.approx(0.80)
