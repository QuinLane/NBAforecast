"""``ModelProvider`` — backend-api.md Prompt 2 + §2.

Loads each head's current champion from the MLflow registry (``training/registry.py``) and holds
it in memory; the API never trains, it only ever calls ``provider.get(head_name).predict(...)``.
``reload()`` hot-swaps in a newly promoted champion — wired to a periodic background poll from
``api/main.py``'s lifespan (the "poll registry version" half of §2's hot-reload decision; reacting
to a Prefect promotion signal directly is deferred until the retraining flow, T6.3, exists).
"""

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from nbaforecast.explain.schema import Explanation
from nbaforecast.models.base import ModelHead

# Re-exported for callers that historically imported it from here; the mapping itself lives in
# models/heads.py so the training driver can share it without importing the API layer. The
# MLflow registry only stores the *fitted model* (a joblib blob); the head class (design-matrix
# selection, explain logic) is looked up in this mapping by name — the API serves whichever
# heads have a champion promoted, and gracefully skips the rest.
from nbaforecast.models.heads import HEAD_REGISTRY as HEAD_REGISTRY
from nbaforecast.training import registry

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class LoadedHead:
    """A head paired with its currently-loaded champion model artifact."""

    head: ModelHead[Any]
    model: Any

    def predict(self, features: pd.DataFrame) -> pd.Series:
        result: pd.Series = self.head.predict(self.model, features)
        return result

    def explain(self, features: pd.DataFrame) -> Explanation:
        return self.head.explain(self.model, features)


class ModelProvider:
    """Holds the current champion model per head; ``reload()`` hot-swaps in a new one."""

    def __init__(self, heads: dict[str, ModelHead[Any]] | None = None) -> None:
        self._heads = heads if heads is not None else HEAD_REGISTRY
        self._models: dict[str, Any] = {}

    def load_all(self) -> None:
        """Load (or refresh) every registered head's champion."""
        for head_name in self._heads:
            self.reload(head_name)

    def reload(self, head_name: str) -> bool:
        """Re-fetch ``head_name``'s champion from MLflow. Returns whether one was found.

        Never raises: a transiently unreachable MLflow server shouldn't crash app startup or a
        background poll tick — it just means this head stays on whatever it had loaded before
        (or unloaded, on the very first attempt), and ``get()`` will surface that as a 503 at the
        router level rather than taking the whole API down.
        """
        try:
            model = registry.load_champion_model(head_name)
        except Exception:
            logger.exception("could not reach MLflow while reloading head %r", head_name)
            return False
        if model is None:
            logger.warning("no champion registered yet for head %r", head_name)
            return False
        self._models[head_name] = model
        logger.info("loaded champion for head %r", head_name)
        return True

    def get(self, head_name: str) -> LoadedHead:
        if head_name not in self._heads:
            raise KeyError(f"unknown model head {head_name!r}")
        model = self._models.get(head_name)
        if model is None:
            raise RuntimeError(f"no champion loaded for head {head_name!r} — call reload() first")
        return LoadedHead(head=self._heads[head_name], model=model)

    def is_loaded(self, head_name: str) -> bool:
        return head_name in self._models
