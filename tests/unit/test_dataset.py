"""Unit tests for the synthetic dataset generator."""

from __future__ import annotations

import pytest

from health_app.predictor.dataset import (
    FEATURE_COLUMNS,
    REGIONS,
    TARGET_COLUMN,
    generate_synthetic_dataset,
)

pytestmark = pytest.mark.unit


def test_dataset_has_expected_columns_and_size() -> None:
    df = generate_synthetic_dataset(n_rows=300, seed=1)
    assert len(df) == 300
    assert list(df.columns) == FEATURE_COLUMNS + [TARGET_COLUMN]


def test_dataset_is_reproducible_with_same_seed() -> None:
    a = generate_synthetic_dataset(n_rows=100, seed=7)
    b = generate_synthetic_dataset(n_rows=100, seed=7)
    assert a.equals(b)


def test_dataset_values_are_in_valid_ranges() -> None:
    df = generate_synthetic_dataset(n_rows=500, seed=2)
    assert df["age"].between(18, 64).all()
    assert df["bmi"].between(16.0, 53.0).all()
    assert df["children"].between(0, 5).all()
    assert df["smoker"].isin(["yes", "no"]).all()
    assert df["sex"].isin(["male", "female"]).all()
    assert df["region"].isin(REGIONS).all()
    assert (df["charges"] > 0).all()


def test_smokers_have_higher_average_charges() -> None:
    """Sanity check: the data-generating process makes smokers cost more."""
    df = generate_synthetic_dataset(n_rows=2_000, seed=3)
    smoker_mean = df.loc[df["smoker"] == "yes", "charges"].mean()
    nonsmoker_mean = df.loc[df["smoker"] == "no", "charges"].mean()
    assert smoker_mean > nonsmoker_mean * 2
