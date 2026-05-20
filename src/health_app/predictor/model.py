"""Quantile-regression cost predictor.

Three gradient-boosted regressors are trained, one per quantile (0.1,
0.5, 0.9). The 0.5 model is the point estimate; the 0.1/0.9 models give
an 80% prediction interval. This is meaningfully better UX than a single
point estimate because healthcare cost distributions are heavy-tailed.

The whole thing wraps a scikit-learn pipeline so categorical features go
through a one-hot step before the booster sees them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from health_app.predictor.schemas import PredictionFeatures

NUMERIC_FEATURES: list[str] = ["age", "bmi", "children"]
CATEGORICAL_FEATURES: list[str] = ["sex", "smoker", "region"]
ALL_FEATURES: list[str] = NUMERIC_FEATURES + CATEGORICAL_FEATURES

DEFAULT_QUANTILES: tuple[float, float, float] = (0.1, 0.5, 0.9)


class CostPrediction(BaseModel):
    """Predicted annual medical charges with an 80% interval."""

    model_config = ConfigDict(frozen=True)

    predicted_charges_cents: int
    lower_bound_cents: int
    upper_bound_cents: int

    @property
    def predicted_charges_dollars(self) -> float:
        return self.predicted_charges_cents / 100

    @property
    def interval_width_cents(self) -> int:
        return self.upper_bound_cents - self.lower_bound_cents


@dataclass
class _TrainedQuantiles:
    """Internal container for the three fitted pipelines, keyed by quantile."""

    pipelines: dict[float, Pipeline]


def _build_pipeline(quantile: float) -> Pipeline:
    """Construct a fresh untrained pipeline for one quantile."""
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore"),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="passthrough",
    )
    regressor = HistGradientBoostingRegressor(
        loss="quantile",
        quantile=quantile,
        max_iter=200,
        max_depth=6,
        learning_rate=0.08,
        random_state=0,
    )
    return Pipeline(
        steps=[("preprocessor", preprocessor), ("regressor", regressor)]
    )


class CostPredictor:
    """Trainable cost predictor with point estimate plus prediction interval."""

    def __init__(
        self,
        quantiles: tuple[float, float, float] = DEFAULT_QUANTILES,
    ) -> None:
        lower, point, upper = quantiles
        if not (0.0 < lower < point < upper < 1.0):
            raise ValueError(
                "quantiles must be three increasing values in (0, 1); "
                f"got {quantiles}"
            )
        self.quantiles = quantiles
        self._trained: _TrainedQuantiles | None = None

    @property
    def is_fitted(self) -> bool:
        return self._trained is not None

    def fit(self, df: pd.DataFrame, target_column: str = "charges") -> "CostPredictor":
        """Fit one regressor per quantile.

        Args:
            df: Training dataframe containing `ALL_FEATURES` and the target.
            target_column: Column name for the regression target.
        """
        missing = set(ALL_FEATURES + [target_column]) - set(df.columns)
        if missing:
            raise ValueError(f"Training data missing columns: {sorted(missing)}")

        X = df[ALL_FEATURES]
        y = df[target_column].to_numpy()

        pipelines: dict[float, Pipeline] = {}
        for q in self.quantiles:
            pipe = _build_pipeline(q)
            pipe.fit(X, y)
            pipelines[q] = pipe
        self._trained = _TrainedQuantiles(pipelines=pipelines)
        return self

    def predict(self, features: PredictionFeatures) -> CostPrediction:
        """Predict charges for a single feature vector."""
        if self._trained is None:
            raise RuntimeError("CostPredictor has not been fitted.")

        df = _features_to_dataframe(features)
        lower_q, point_q, upper_q = self.quantiles
        lower = float(self._trained.pipelines[lower_q].predict(df)[0])
        point = float(self._trained.pipelines[point_q].predict(df)[0])
        upper = float(self._trained.pipelines[upper_q].predict(df)[0])

        # Clamp lower at zero; enforce ordering so the interval is sane
        # even if quantile predictions cross (rare with small data).
        lower = max(0.0, lower)
        point = max(lower, point)
        upper = max(point, upper)

        return CostPrediction(
            predicted_charges_cents=_dollars_to_cents(point),
            lower_bound_cents=_dollars_to_cents(lower),
            upper_bound_cents=_dollars_to_cents(upper),
        )

    def predict_many(
        self, feature_rows: list[PredictionFeatures]
    ) -> list[CostPrediction]:
        """Batch predict for many feature vectors.

        Avoids re-invoking the pipelines per row, which is much faster
        for what-if sweeps with dozens of points.
        """
        if self._trained is None:
            raise RuntimeError("CostPredictor has not been fitted.")
        if not feature_rows:
            return []

        df = pd.DataFrame([f.model_dump() for f in feature_rows])[ALL_FEATURES]
        lower_q, point_q, upper_q = self.quantiles
        lower = self._trained.pipelines[lower_q].predict(df)
        point = self._trained.pipelines[point_q].predict(df)
        upper = self._trained.pipelines[upper_q].predict(df)

        lower = np.maximum(0.0, lower)
        point = np.maximum(lower, point)
        upper = np.maximum(point, upper)

        return [
            CostPrediction(
                predicted_charges_cents=_dollars_to_cents(point[i]),
                lower_bound_cents=_dollars_to_cents(lower[i]),
                upper_bound_cents=_dollars_to_cents(upper[i]),
            )
            for i in range(len(feature_rows))
        ]

    def save(self, path: Path | str) -> None:
        """Persist the trained pipelines to disk."""
        if self._trained is None:
            raise RuntimeError("Nothing to save; predictor has not been fitted.")
        joblib.dump(
            {"quantiles": self.quantiles, "pipelines": self._trained.pipelines},
            path,
        )

    @classmethod
    def load(cls, path: Path | str) -> "CostPredictor":
        """Load a previously saved predictor."""
        blob = joblib.load(path)
        inst = cls(quantiles=tuple(blob["quantiles"]))
        inst._trained = _TrainedQuantiles(pipelines=blob["pipelines"])
        return inst


def _features_to_dataframe(features: PredictionFeatures) -> pd.DataFrame:
    """Wrap a single PredictionFeatures into the shape the pipeline expects."""
    return pd.DataFrame([features.model_dump()])[ALL_FEATURES]


def _dollars_to_cents(amount: float) -> int:
    """Round and clamp a dollar amount into non-negative whole cents."""
    return max(0, int(round(amount * 100)))
