"""Module entry point: `uvicorn health_app.main:app`.

Trains (or loads from cache) the cost predictor on startup, then wires
it to the FastAPI app along with the seeded benefits repository.

Dataset resolution order:

1. `HEALTH_APP_DATASET_CSV` env var, if set, must point to a CSV.
2. `data/insurance.csv` relative to the project root, if present.
3. Synthetic Kaggle-shaped dataset, generated deterministically.

The model cache is keyed by the chosen data source so swapping inputs
forces a clean retrain instead of silently reusing the old model.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from health_app.api import create_app
from health_app.benefits.seed import build_default_repository
from health_app.docchat.llm import auto_select_llm
from health_app.docchat.service import DocumentChatService
from health_app.predictor.dataset import load_dataset
from health_app.predictor.model import CostPredictor

# Path to the repo's optional local dataset. Resolved relative to this file
# so it works regardless of the current working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_DATASET_PATH = _REPO_ROOT / "data" / "insurance.csv"

_CACHE_DIR = Path(
    os.environ.get(
        "HEALTH_APP_CACHE_DIR",
        str(Path.home() / ".cache" / "health_app"),
    )
)


def _resolve_dataset_source() -> tuple[str, Path | None]:
    """Pick the dataset and return (source_tag, optional_csv_path).

    The source tag is used to namespace the model cache file so swapping
    datasets forces a retrain.
    """
    env_csv = os.environ.get("HEALTH_APP_DATASET_CSV")
    if env_csv:
        return f"env:{env_csv}", Path(env_csv)
    if _LOCAL_DATASET_PATH.exists():
        return f"file:{_LOCAL_DATASET_PATH}", _LOCAL_DATASET_PATH
    return "synthetic", None


def _cache_path_for(source_tag: str) -> Path:
    """Stable, source-keyed cache file path."""
    digest = hashlib.sha1(source_tag.encode("utf-8")).hexdigest()[:12]
    return _CACHE_DIR / f"cost_predictor.{digest}.joblib"


def _load_or_train_predictor() -> CostPredictor:
    """Return a fitted predictor, training and caching on first run."""
    source_tag, csv_path = _resolve_dataset_source()
    cache_path = _cache_path_for(source_tag)

    if cache_path.exists():
        return CostPredictor.load(cache_path)

    predictor = CostPredictor()
    predictor.fit(load_dataset(csv_path=csv_path))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    predictor.save(cache_path)
    return predictor


app = create_app(
    repository=build_default_repository(),
    predictor=_load_or_train_predictor(),
    chat_service=DocumentChatService(llm=auto_select_llm()),
)
