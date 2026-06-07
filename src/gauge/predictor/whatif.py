"""What-if simulator.

Holds a baseline feature vector fixed, varies a single feature across a list
of values, and returns the prediction at each value. When a plan is supplied,
each prediction's conformal charge interval is propagated through the plan to
produce an ``OopInterval`` alongside the raw prediction.

The sweep is implemented with batched prediction so dozens of points run in
roughly the same time as a single point.
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict

from gauge.benefits.models import Plan
from gauge.predictor.annual_cost import OopInterval, oop_interval_from_prediction
from gauge.predictor.model import CostPrediction, CostPredictor
from gauge.predictor.schemas import PredictionFeatures

SweepValue = Union[int, float, str]
SWEEPABLE_FEATURES: frozenset[str] = frozenset(PredictionFeatures.model_fields)


class WhatIfPoint(BaseModel):
    """A single point on a what-if sweep.

    Parameters
    ----------
    value : int, float, or str
        The substituted feature value at this point.
    prediction : CostPrediction
        Predicted charges at this value (median, mean, conformal interval).
    oop_interval : OopInterval or None
        Conformal OOP interval obtained by propagating ``prediction`` through
        the plan. ``None`` when no plan was provided to :func:`sweep`.
    """

    model_config = ConfigDict(frozen=True)

    value: SweepValue
    prediction: CostPrediction
    oop_interval: OopInterval | None = None


class WhatIfResponse(BaseModel):
    """Result of varying one feature across a list of values.

    Parameters
    ----------
    feature : str
        The name of the swept feature.
    points : list[WhatIfPoint]
        One entry per value in the sweep, in the same order.
    """

    model_config = ConfigDict(frozen=True)

    feature: str
    points: list[WhatIfPoint]


def sweep(
    predictor: CostPredictor,
    baseline: PredictionFeatures,
    feature: str,
    values: list[SweepValue],
    plan: Plan | None = None,
) -> WhatIfResponse:
    """Sweep one feature across a list of values and return the prediction curve.

    Holds the baseline vector fixed except for ``feature``, substitutes each
    value in ``values``, and runs batched prediction over all resulting rows.
    When a plan is provided, each prediction's conformal charge interval is
    propagated through the plan to give an ``OopInterval`` at each point.

    Parameters
    ----------
    predictor : CostPredictor
        A fitted :class:`~gauge.predictor.model.CostPredictor`.
    baseline : PredictionFeatures
        Feature vector held constant except for ``feature``.
    feature : str
        Name of the feature to vary. Must be a field of
        :class:`~gauge.predictor.schemas.PredictionFeatures`.
    values : list[SweepValue]
        Values to substitute for ``feature``. Each must validate against
        the field's type.
    plan : Plan or None, optional
        When provided, each prediction's conformal interval is propagated
        through the plan to produce an :class:`~gauge.predictor.annual_cost.OopInterval`.

    Returns
    -------
    WhatIfResponse
        Response whose ``points`` are aligned to ``values``.

    Raises
    ------
    ValueError
        If ``feature`` is not a sweepable field or any value in ``values``
        fails validation against that field's type.
    """
    if feature not in SWEEPABLE_FEATURES:
        raise ValueError(
            f"Cannot sweep {feature!r}; valid features are "
            f"{sorted(SWEEPABLE_FEATURES)}."
        )
    if not values:
        return WhatIfResponse(feature=feature, points=[])

    # Re-validate each modified vector through the model so bad values
    # surface here with a clean error rather than crashing the pipeline
    # downstream. (model_copy(update=...) intentionally skips validation.)
    base_payload = baseline.model_dump()
    feature_rows: list[PredictionFeatures] = []
    for v in values:
        try:
            feature_rows.append(
                PredictionFeatures.model_validate({**base_payload, feature: v})
            )
        except Exception as e:
            raise ValueError(
                f"Invalid value {v!r} for feature {feature!r}: {e}"
            ) from e
    predictions = predictor.predict_many(feature_rows)

    points: list[WhatIfPoint] = []
    for value, prediction in zip(values, predictions):
        interval = oop_interval_from_prediction(plan, prediction) if plan is not None else None
        points.append(WhatIfPoint(value=value, prediction=prediction, oop_interval=interval))

    return WhatIfResponse(feature=feature, points=points)
