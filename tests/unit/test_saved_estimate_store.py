"""Unit tests for InMemorySavedEstimateStore and SqliteSavedEstimateStore.

Tests verify:
- CRUD operations (save, list, get, rename, delete).
- User isolation: one user cannot see or mutate another's estimates.
- Ownership enforcement: rename and delete raise PermissionError for wrong user.
- SQLite persistence: data survives a close + reopen cycle.
- Thread safety under concurrent writes.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from gauge.predictor.model import CostPrediction
from gauge.predictor.schemas import PredictionFeatures
from gauge.saved_estimates.models import InMemorySavedEstimateStore
from gauge.saved_estimates.sqlite_store import SqliteSavedEstimateStore

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _features() -> PredictionFeatures:
    return PredictionFeatures(
        age=35, sex="female", bmi=27.5, children=1, smoker="no", region="northeast"
    )


def _prediction() -> CostPrediction:
    return CostPrediction(
        median_charges_cents=500_000,
        mean_charges_cents=520_000,
        lower_bound_cents=300_000,
        upper_bound_cents=800_000,
        conformal_calibrated=True,
        calibration_coverage=0.80,
    )


def _save(store, user_id: str = "user-a", label: str = "My Estimate"):
    """Convenience wrapper that saves one estimate and returns it."""
    return store.save(
        user_id=user_id,
        label=label,
        features=_features(),
        prediction=_prediction(),
        plan=None,
        oop_interval=None,
    )


# ---------------------------------------------------------------------------
# Parametrised store factory so the same tests run for both backends.
# ---------------------------------------------------------------------------


def _make_in_memory() -> InMemorySavedEstimateStore:
    return InMemorySavedEstimateStore()


def _make_sqlite(tmp_path: Path) -> SqliteSavedEstimateStore:
    return SqliteSavedEstimateStore(tmp_path / "test.db")


# ---------------------------------------------------------------------------
# InMemorySavedEstimateStore — CRUD
# ---------------------------------------------------------------------------


class TestInMemoryStoreCRUD:
    def test_save_returns_estimate_with_id(self) -> None:
        store = _make_in_memory()
        est = _save(store)
        assert est.id
        assert est.label == "My Estimate"
        assert est.user_id == "user-a"
        assert est.oop_interval is None
        assert est.plan is None

    def test_get_returns_saved_estimate(self) -> None:
        store = _make_in_memory()
        est = _save(store)
        fetched = store.get(est.id)
        assert fetched is not None
        assert fetched.id == est.id

    def test_get_missing_returns_none(self) -> None:
        store = _make_in_memory()
        assert store.get("ghost") is None

    def test_list_returns_all_for_user(self) -> None:
        store = _make_in_memory()
        for i in range(3):
            _save(store, label=f"Est {i}")
        estimates = store.list("user-a")
        assert len(estimates) == 3

    def test_list_sorted_newest_first(self) -> None:
        store = _make_in_memory()
        for i in range(3):
            _save(store, label=f"Est {i}")
        labels = [e.label for e in store.list("user-a")]
        # Python dict preserves insertion order; newest-first means reversed.
        assert labels == ["Est 2", "Est 1", "Est 0"]

    def test_list_empty_for_unknown_user(self) -> None:
        store = _make_in_memory()
        _save(store, user_id="user-a")
        assert store.list("user-b") == []

    def test_rename_updates_label(self) -> None:
        store = _make_in_memory()
        est = _save(store)
        updated = store.rename(est.id, "user-a", "Renamed")
        assert updated.label == "Renamed"

    def test_rename_reflects_in_list(self) -> None:
        store = _make_in_memory()
        est = _save(store)
        store.rename(est.id, "user-a", "New Name")
        assert store.list("user-a")[0].label == "New Name"

    def test_rename_missing_raises_key_error(self) -> None:
        store = _make_in_memory()
        with pytest.raises(KeyError):
            store.rename("ghost", "user-a", "X")

    def test_rename_wrong_user_raises_permission_error(self) -> None:
        store = _make_in_memory()
        est = _save(store, user_id="user-a")
        with pytest.raises(PermissionError):
            store.rename(est.id, "user-b", "Stolen")

    def test_delete_removes_estimate(self) -> None:
        store = _make_in_memory()
        est = _save(store)
        store.delete(est.id, "user-a")
        assert store.get(est.id) is None
        assert store.list("user-a") == []

    def test_delete_missing_raises_key_error(self) -> None:
        store = _make_in_memory()
        with pytest.raises(KeyError):
            store.delete("ghost", "user-a")

    def test_delete_wrong_user_raises_permission_error(self) -> None:
        store = _make_in_memory()
        est = _save(store, user_id="user-a")
        with pytest.raises(PermissionError):
            store.delete(est.id, "user-b")


# ---------------------------------------------------------------------------
# InMemorySavedEstimateStore — user isolation
# ---------------------------------------------------------------------------


class TestInMemoryStoreUserIsolation:
    def test_list_does_not_cross_users(self) -> None:
        store = _make_in_memory()
        _save(store, user_id="alice", label="Alice Est")
        _save(store, user_id="bob", label="Bob Est")
        assert len(store.list("alice")) == 1
        assert len(store.list("bob")) == 1
        assert store.list("alice")[0].label == "Alice Est"
        assert store.list("bob")[0].label == "Bob Est"

    def test_each_save_gets_unique_id(self) -> None:
        store = _make_in_memory()
        ids = {_save(store, label=f"E{i}").id for i in range(10)}
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# SqliteSavedEstimateStore — CRUD
# ---------------------------------------------------------------------------


class TestSqliteStoreCRUD:
    def test_save_returns_estimate_with_id(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        est = _save(store)
        assert est.id
        assert est.label == "My Estimate"
        assert est.user_id == "user-a"

    def test_get_returns_saved_estimate(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        est = _save(store)
        fetched = store.get(est.id)
        assert fetched is not None
        assert fetched.id == est.id
        assert fetched.features.age == 35

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        assert store.get("ghost") is None

    def test_list_returns_all_for_user(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        for i in range(3):
            _save(store, label=f"Est {i}")
        assert len(store.list("user-a")) == 3

    def test_list_sorted_newest_first(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        for i in range(3):
            _save(store, label=f"Est {i}")
        labels = [e.label for e in store.list("user-a")]
        assert labels == ["Est 2", "Est 1", "Est 0"]

    def test_list_empty_for_unknown_user(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        _save(store, user_id="user-a")
        assert store.list("user-b") == []

    def test_rename_updates_label(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        est = _save(store)
        updated = store.rename(est.id, "user-a", "Renamed")
        assert updated.label == "Renamed"
        assert store.get(est.id).label == "Renamed"

    def test_rename_missing_raises_key_error(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        with pytest.raises(KeyError):
            store.rename("ghost", "user-a", "X")

    def test_rename_wrong_user_raises_permission_error(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        est = _save(store, user_id="user-a")
        with pytest.raises(PermissionError):
            store.rename(est.id, "user-b", "Stolen")

    def test_delete_removes_estimate(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        est = _save(store)
        store.delete(est.id, "user-a")
        assert store.get(est.id) is None

    def test_delete_missing_raises_key_error(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        with pytest.raises(KeyError):
            store.delete("ghost", "user-a")

    def test_delete_wrong_user_raises_permission_error(self, tmp_path: Path) -> None:
        store = _make_sqlite(tmp_path)
        est = _save(store, user_id="user-a")
        with pytest.raises(PermissionError):
            store.delete(est.id, "user-b")


# ---------------------------------------------------------------------------
# SqliteSavedEstimateStore — persistence across reconnect
# ---------------------------------------------------------------------------


class TestSqliteStorePersistence:
    def test_estimate_survives_close_and_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        store1 = SqliteSavedEstimateStore(db)
        est = _save(store1)
        store1.close()

        store2 = SqliteSavedEstimateStore(db)
        fetched = store2.get(est.id)
        assert fetched is not None
        assert fetched.label == "My Estimate"
        assert fetched.features.age == 35
        assert fetched.prediction.median_charges_cents == 500_000

    def test_rename_persists_across_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        store1 = SqliteSavedEstimateStore(db)
        est = _save(store1)
        store1.rename(est.id, "user-a", "Persisted Label")
        store1.close()

        store2 = SqliteSavedEstimateStore(db)
        assert store2.get(est.id).label == "Persisted Label"

    def test_delete_persists_across_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        store1 = SqliteSavedEstimateStore(db)
        est = _save(store1)
        store1.delete(est.id, "user-a")
        store1.close()

        store2 = SqliteSavedEstimateStore(db)
        assert store2.get(est.id) is None
        assert store2.list("user-a") == []

    def test_multiple_estimates_survive_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        store1 = SqliteSavedEstimateStore(db)
        saved_ids = [_save(store1, label=f"Est {i}").id for i in range(5)]
        store1.close()

        store2 = SqliteSavedEstimateStore(db)
        for est_id in saved_ids:
            assert store2.get(est_id) is not None

    def test_user_isolation_persists_across_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        store1 = SqliteSavedEstimateStore(db)
        _save(store1, user_id="alice")
        _save(store1, user_id="bob")
        store1.close()

        store2 = SqliteSavedEstimateStore(db)
        assert len(store2.list("alice")) == 1
        assert len(store2.list("bob")) == 1


# ---------------------------------------------------------------------------
# SqliteSavedEstimateStore — thread safety
# ---------------------------------------------------------------------------


class TestSqliteStoreThreadSafety:
    def test_concurrent_saves_all_persist(self, tmp_path: Path) -> None:
        store = SqliteSavedEstimateStore(tmp_path / "test.db")
        errors: list[Exception] = []

        def save_one(i: int) -> None:
            try:
                _save(store, user_id=f"user-{i}", label=f"Est {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=save_one, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        total = sum(len(store.list(f"user-{i}")) for i in range(30))
        assert total == 30
