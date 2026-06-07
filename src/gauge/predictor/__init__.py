"""Annual medical cost predictor and what-if simulator.

Public surface:

* `PredictionFeatures`, `CostPrediction`: pydantic schemas for the model.
* `CostPredictor`: quantile-regression ensemble (10th, 50th, 90th percentile).
* `sweep`: vary one feature across values and compare predictions.
* `apply_plan_to_annual_spend`: bridge predicted charges into the benefits
  engine to produce an ``AnnualPlanShare`` breakdown for a single charge figure.
* `oop_interval_from_prediction`: propagate a conformal charge interval through
  a plan to obtain a coverage-preserving ``OopInterval``.
"""

from gauge.predictor.annual_cost import (
    AnnualPlanShare,
    OopInterval,
    apply_plan_to_annual_spend,
    oop_interval_from_prediction,
)
from gauge.predictor.dataset import generate_synthetic_dataset, load_dataset
from gauge.predictor.model import CostPrediction, CostPredictor
from gauge.predictor.schemas import PredictionFeatures
from gauge.predictor.whatif import WhatIfPoint, WhatIfResponse, sweep

__all__ = [
    "AnnualPlanShare",
    "CostPrediction",
    "CostPredictor",
    "OopInterval",
    "PredictionFeatures",
    "WhatIfPoint",
    "WhatIfResponse",
    "apply_plan_to_annual_spend",
    "generate_synthetic_dataset",
    "load_dataset",
    "oop_interval_from_prediction",
    "sweep",
]
