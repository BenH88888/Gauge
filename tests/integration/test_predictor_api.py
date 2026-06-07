"""Integration tests for the predictor API surface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gauge.api import create_app
from gauge.benefits.repository import InMemoryRepository
from gauge.predictor.model import CostPredictor

pytestmark = pytest.mark.integration


@pytest.fixture
def client(
    seeded_repository: InMemoryRepository,
    trained_predictor: CostPredictor,
) -> TestClient:
    return TestClient(create_app(seeded_repository, trained_predictor))


def _baseline_payload() -> dict:
    return {
        "age": 35,
        "sex": "female",
        "bmi": 27.5,
        "children": 1,
        "smoker": "no",
        "region": "northeast",
    }


class TestPredict:
    def test_predict_returns_interval(self, client: TestClient) -> None:
        response = client.post("/predict", json={"features": _baseline_payload()})
        assert response.status_code == 200
        body = response.json()
        pred = body["prediction"]
        assert pred["lower_bound_cents"] <= pred["median_charges_cents"]
        assert pred["median_charges_cents"] <= pred["upper_bound_cents"]
        assert pred["mean_charges_cents"] >= 0
        # No plan — OOP interval should be absent.
        assert body["oop_interval"] is None
        assert pred["conformal_calibrated"] is True
        assert pred["calibration_coverage"] == pytest.approx(0.80)

    def test_predict_with_plan_returns_oop_interval(self, client: TestClient) -> None:
        response = client.post(
            "/predict",
            json={"features": _baseline_payload(), "plan_id": "ppo_gold"},
        )
        assert response.status_code == 200
        body = response.json()
        interval = body["oop_interval"]
        assert interval is not None
        # OOP interval must be monotone.
        assert interval["lower_cents"] <= interval["median_cents"]
        assert interval["median_cents"] <= interval["upper_cents"]
        # Coverage inherited from the conformal prediction.
        assert interval["coverage"] == pytest.approx(0.80)

    def test_predict_unknown_plan_404(self, client: TestClient) -> None:
        response = client.post(
            "/predict",
            json={"features": _baseline_payload(), "plan_id": "missing"},
        )
        assert response.status_code == 404

    def test_predict_validation_rejects_bad_age(self, client: TestClient) -> None:
        bad = _baseline_payload() | {"age": -5}
        response = client.post("/predict", json={"features": bad})
        assert response.status_code == 422

    def test_predict_validation_rejects_bad_region(self, client: TestClient) -> None:
        bad = _baseline_payload() | {"region": "atlantis"}
        response = client.post("/predict", json={"features": bad})
        assert response.status_code == 422


class TestWhatIf:
    def test_whatif_age_sweep(self, client: TestClient) -> None:
        response = client.post(
            "/whatif",
            json={
                "baseline": _baseline_payload(),
                "feature": "age",
                "values": [25, 40, 55],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["feature"] == "age"
        assert [p["value"] for p in body["points"]] == [25, 40, 55]

    def test_whatif_without_plan_has_no_oop_interval(self, client: TestClient) -> None:
        response = client.post(
            "/whatif",
            json={
                "baseline": _baseline_payload(),
                "feature": "age",
                "values": [30, 40],
            },
        )
        assert response.status_code == 200
        for point in response.json()["points"]:
            assert point["oop_interval"] is None

    def test_whatif_with_plan_includes_oop_interval(self, client: TestClient) -> None:
        response = client.post(
            "/whatif",
            json={
                "baseline": _baseline_payload(),
                "feature": "smoker",
                "values": ["no", "yes"],
                "plan_id": "ppo_gold",
            },
        )
        assert response.status_code == 200
        for point in response.json()["points"]:
            interval = point["oop_interval"]
            assert interval is not None
            assert interval["lower_cents"] <= interval["median_cents"]
            assert interval["median_cents"] <= interval["upper_cents"]

    def test_whatif_rejects_unknown_feature(self, client: TestClient) -> None:
        response = client.post(
            "/whatif",
            json={
                "baseline": _baseline_payload(),
                "feature": "magic",
                "values": [1, 2, 3],
            },
        )
        # Literal[...] validation kicks in at the request body level.
        assert response.status_code == 422

    def test_whatif_unknown_plan_404(self, client: TestClient) -> None:
        response = client.post(
            "/whatif",
            json={
                "baseline": _baseline_payload(),
                "feature": "age",
                "values": [30],
                "plan_id": "missing",
            },
        )
        assert response.status_code == 404
