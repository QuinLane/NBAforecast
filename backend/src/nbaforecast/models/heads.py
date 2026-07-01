"""The canonical head registry — head name → ``ModelHead`` instance (roadmap.md §1).

One shared mapping so the API's ``ModelProvider`` (serving) and the training driver
(``entrypoints/train.py``) can never disagree about which class answers to a head name. The
name keys double as MLflow experiment names (``training/registry.py``), so a mismatch here
would silently train one head and serve another.
"""

from typing import Any

from nbaforecast.models.base import ModelHead
from nbaforecast.models.game_prediction.margin import LightGBMMarginHead
from nbaforecast.models.game_prediction.total import LightGBMTotalHead
from nbaforecast.models.game_prediction.win_prob import LightGBMWinProbHead
from nbaforecast.models.props.regressor import PropsRegressorHead

PROPS_STATS: tuple[str, ...] = ("pts", "reb", "ast", "fg3m")

HEAD_REGISTRY: dict[str, ModelHead[Any]] = {
    "game_win": LightGBMWinProbHead(),
    "game_margin": LightGBMMarginHead(),
    "game_total": LightGBMTotalHead(),
    **{f"props_{stat}": PropsRegressorHead(stat) for stat in PROPS_STATS},
}
