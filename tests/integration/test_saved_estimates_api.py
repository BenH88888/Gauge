"""Integration tests for the saved-estimates API endpoints.

Exercises all four routes via FastAPI's ``TestClient``:

  POST   /saved-estimates          (save)
  GET    /saved-estimates          (list)
  PATCH  /saved-estimates/{id}     (rename)
  DELETE /saved-estimates/{id}     (delete)

Each test class is scoped to one endpoint and covers the happy path,
authentication errors (missing / wrong header), authorisation errors
(wrong user → 403), and not-found errors (404).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gauge.api import create_app
from gauge.benefits.repository import InMemoryRepository
from gauge.docchat.llm import EchoLLM
from gauge.docchat.service import DocumentChatService
from gauge.plan_extract.extractor import PlanExtractor
from gauge.predictor.model import CostPredictor
from gauge.saved_estimates.models import InMemorySavedEstimateStore
from gauge.session.store import InMemorySessionStore

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(
    seeded_repository: InMemoryRepository,
    trained_predictor: CostPredictor,
) -> TestClient:
    """Fresh app with isolated in-memory stores and EchoLLM for every test."""
    llm = EchoLLM()
    chat_service = DocumentChatService(llm=llm)
    return TestClient(
        create_app(
            repository=seeded_repository,
            predictor=trained_predictor,
            chat_service=chat_service,
            session_store=InMemorySessionStore(),
            plan_extractor=PlanExtractor(llm=llm),
            saved_estimate_store=InMemorySavedEstimateStore(),
        )
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_USER_A = "aaaaaaaa-0000-0000-0000-000000000001"
_USER_B = "bbbbbbbb-0000-0000-0000-000000000002"

_FEATURES = {
    "age": 35,
    "sex": "female",
    "bmi": 27.5,
    "children": 1,
    "smoker": "no",
    "region": "northeast",
}

_PLAN_PAYLOAD = {
    "deductible_cents": 150_000,
    "out_of_pocket_max_cents": 600_000,
    "coinsurance_rate": 0.20,
    "copays_cents": {},
    "plan_name": "Test Plan",
}


def _create_session(client: TestClient, user_id: str = _USER_A) -> str:
    """Create a session and return its ID.

    The session creation endpoint does not require ``X-Gauge-User-Id``, but
    passing it is harmless and keeps callers consistent.
    """
    resp = client.post("/sessions", json={"features": _FEATURES})
    assert resp.status_code == 200
    return resp.json()["session_id"]


def _confirm_plan(client: TestClient, session_id: str) -> None:
    """Confirm a plan on the session so it can be saved."""
    resp = client.post(f"/sessions/{session_id}/plan", json=_PLAN_PAYLOAD)
    assert resp.status_code == 200


def _save_estimate(
    client: TestClient,
    session_id: str,
    label: str = "Test Estimate",
    user_id: str = _USER_A,
) -> dict:
    """Confirm the session plan (required by the API) then save an estimate.

    Returns the response body of POST /saved-estimates (status 201).
    """
    _confirm_plan(client, session_id)
    resp = client.post(
        "/saved-estimates",
        json={"session_id": session_id, "label": label},
        headers={"X-Gauge-User-Id": user_id},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# POST /saved-estimates
# ---------------------------------------------------------------------------


class TestSaveEstimate:
    def test_happy_path_returns_estimate(self, client: TestClient) -> None:
        sid = _create_session(client)
        body = _save_estimate(client, sid)
        assert body["id"]
        assert body["label"] == "Test Estimate"
        assert body["user_id"] == _USER_A
        assert body["features"]["age"] == 35
        assert body["prediction"]["median_charges_cents"] >= 0

    def test_plan_and_oop_interval_present_after_save(self, client: TestClient) -> None:
        """Saving always requires a confirmed plan, so plan/oop_interval are non-null."""
        sid = _create_session(client)
        body = _save_estimate(client, sid)
        assert body["plan"] is not None
        assert body["oop_interval"] is not None

    def test_no_plan_confirmed_returns_400(self, client: TestClient) -> None:
        """Saving without confirming a plan first returns 400."""
        sid = _create_session(client)
        resp = client.post(
            "/saved-estimates",
            json={"session_id": sid, "label": "Too Early"},
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 400

    def test_missing_user_id_header_returns_422(self, client: TestClient) -> None:
        sid = _create_session(client)
        _confirm_plan(client, sid)
        resp = client.post(
            "/saved-estimates",
            json={"session_id": sid, "label": "No Header"},
        )
        assert resp.status_code == 422

    def test_unknown_session_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/saved-estimates",
            json={"session_id": "ghost-session", "label": "Ghost"},
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 404

    def test_empty_label_returns_422(self, client: TestClient) -> None:
        sid = _create_session(client)
        _confirm_plan(client, sid)
        resp = client.post(
            "/saved-estimates",
            json={"session_id": sid, "label": ""},
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 422

    def test_label_too_long_returns_422(self, client: TestClient) -> None:
        sid = _create_session(client)
        _confirm_plan(client, sid)
        resp = client.post(
            "/saved-estimates",
            json={"session_id": sid, "label": "x" * 121},
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /saved-estimates
# ---------------------------------------------------------------------------


class TestListEstimates:
    def test_empty_list_for_new_user(self, client: TestClient) -> None:
        resp = client.get(
            "/saved-estimates",
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_saved_estimates_for_user(self, client: TestClient) -> None:
        sid = _create_session(client)
        _save_estimate(client, sid, label="First")
        _save_estimate(client, sid, label="Second")
        resp = client.get(
            "/saved-estimates",
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 200
        labels = [e["label"] for e in resp.json()]
        assert set(labels) == {"First", "Second"}

    def test_sorted_newest_first(self, client: TestClient) -> None:
        sid = _create_session(client)
        for i in range(3):
            _save_estimate(client, sid, label=f"Est {i}")
        resp = client.get(
            "/saved-estimates",
            headers={"X-Gauge-User-Id": _USER_A},
        )
        labels = [e["label"] for e in resp.json()]
        assert labels == ["Est 2", "Est 1", "Est 0"]

    def test_does_not_return_other_users_estimates(self, client: TestClient) -> None:
        sid_a = _create_session(client, user_id=_USER_A)
        sid_b = _create_session(client, user_id=_USER_B)
        _save_estimate(client, sid_a, label="Alice's Est", user_id=_USER_A)
        _save_estimate(client, sid_b, label="Bob's Est", user_id=_USER_B)

        resp_a = client.get("/saved-estimates", headers={"X-Gauge-User-Id": _USER_A})
        resp_b = client.get("/saved-estimates", headers={"X-Gauge-User-Id": _USER_B})

        assert [e["label"] for e in resp_a.json()] == ["Alice's Est"]
        assert [e["label"] for e in resp_b.json()] == ["Bob's Est"]

    def test_missing_user_id_header_returns_422(self, client: TestClient) -> None:
        resp = client.get("/saved-estimates")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /saved-estimates/{id}
# ---------------------------------------------------------------------------


class TestRenameEstimate:
    def test_happy_path_returns_updated_estimate(self, client: TestClient) -> None:
        sid = _create_session(client)
        est = _save_estimate(client, sid)
        resp = client.patch(
            f"/saved-estimates/{est['id']}",
            json={"label": "Renamed"},
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 200
        assert resp.json()["label"] == "Renamed"

    def test_rename_visible_in_list(self, client: TestClient) -> None:
        sid = _create_session(client)
        est = _save_estimate(client, sid)
        client.patch(
            f"/saved-estimates/{est['id']}",
            json={"label": "New Name"},
            headers={"X-Gauge-User-Id": _USER_A},
        )
        resp = client.get("/saved-estimates", headers={"X-Gauge-User-Id": _USER_A})
        assert resp.json()[0]["label"] == "New Name"

    def test_missing_user_id_header_returns_422(self, client: TestClient) -> None:
        sid = _create_session(client)
        est = _save_estimate(client, sid)
        resp = client.patch(
            f"/saved-estimates/{est['id']}",
            json={"label": "Renamed"},
        )
        assert resp.status_code == 422

    def test_wrong_user_returns_403(self, client: TestClient) -> None:
        sid = _create_session(client, user_id=_USER_A)
        est = _save_estimate(client, sid, user_id=_USER_A)
        resp = client.patch(
            f"/saved-estimates/{est['id']}",
            json={"label": "Stolen"},
            headers={"X-Gauge-User-Id": _USER_B},
        )
        assert resp.status_code == 403

    def test_unknown_estimate_returns_404(self, client: TestClient) -> None:
        resp = client.patch(
            "/saved-estimates/does-not-exist",
            json={"label": "X"},
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 404

    def test_empty_label_returns_422(self, client: TestClient) -> None:
        sid = _create_session(client)
        est = _save_estimate(client, sid)
        resp = client.patch(
            f"/saved-estimates/{est['id']}",
            json={"label": ""},
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /saved-estimates/{id}
# ---------------------------------------------------------------------------


class TestDeleteEstimate:
    def test_happy_path_returns_204(self, client: TestClient) -> None:
        sid = _create_session(client)
        est = _save_estimate(client, sid)
        resp = client.delete(
            f"/saved-estimates/{est['id']}",
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 204

    def test_deleted_estimate_absent_from_list(self, client: TestClient) -> None:
        sid = _create_session(client)
        est = _save_estimate(client, sid)
        client.delete(
            f"/saved-estimates/{est['id']}",
            headers={"X-Gauge-User-Id": _USER_A},
        )
        resp = client.get("/saved-estimates", headers={"X-Gauge-User-Id": _USER_A})
        assert resp.json() == []

    def test_missing_user_id_header_returns_422(self, client: TestClient) -> None:
        sid = _create_session(client)
        est = _save_estimate(client, sid)
        resp = client.delete(f"/saved-estimates/{est['id']}")
        assert resp.status_code == 422

    def test_wrong_user_returns_403(self, client: TestClient) -> None:
        sid = _create_session(client, user_id=_USER_A)
        est = _save_estimate(client, sid, user_id=_USER_A)
        resp = client.delete(
            f"/saved-estimates/{est['id']}",
            headers={"X-Gauge-User-Id": _USER_B},
        )
        assert resp.status_code == 403

    def test_unknown_estimate_returns_404(self, client: TestClient) -> None:
        resp = client.delete(
            "/saved-estimates/does-not-exist",
            headers={"X-Gauge-User-Id": _USER_A},
        )
        assert resp.status_code == 404

    def test_wrong_user_estimate_still_visible_to_owner(self, client: TestClient) -> None:
        """A 403 rejection must not delete the estimate."""
        sid = _create_session(client, user_id=_USER_A)
        est = _save_estimate(client, sid, user_id=_USER_A)
        client.delete(
            f"/saved-estimates/{est['id']}",
            headers={"X-Gauge-User-Id": _USER_B},
        )
        resp = client.get("/saved-estimates", headers={"X-Gauge-User-Id": _USER_A})
        assert len(resp.json()) == 1
