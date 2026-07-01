"""Props projection service — backend-api.md §3 (``/players/{id}/props``) + Prompt 5.

Mirrors ``services/games.py``'s prediction path, but over ``features_player_game`` and the props
champion heads: build the player's feature row for the game (train/serve parity handles both
completed and scheduled games), then for each stat call the champion ``props_{stat}`` head for a
point estimate, prediction interval, and SHAP explanation.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api.model_provider import ModelProvider
from nbaforecast.api.schemas.players import PropsProjection
from nbaforecast.explain.humanizer import humanize
from nbaforecast.features.player_game import build_player_game_features
from nbaforecast.models.props.regressor import PropsRegressorHead
from nbaforecast.storage.models import Game, Player, PlayerGameStats, TeamGameStats
from nbaforecast.storage.repositories import load_table_as_dataframe

PROPS_STATS: tuple[str, ...] = ("pts", "reb", "ast", "fg3m")
TOP_N_DRIVERS = 5


async def player_props(
    session: AsyncSession,
    model_provider: ModelProvider,
    player_id: int,
    game_id: str,
    *,
    stats: tuple[str, ...] = PROPS_STATS,
    full: bool = False,
) -> list[PropsProjection] | None:
    """``GET /players/{player_id}/props?game_id=`` — PTS/REB/AST/3PM projections + intervals.

    Returns ``None`` (router → 404) when the game or player doesn't exist, or the player has no
    feature row for that game (e.g. no prior games to build rolling features from). Propagates
    ``RuntimeError`` from ``ModelProvider.get`` when no props champion is loaded (router → 503).
    """
    game = await session.get(Game, game_id)
    player = await session.get(Player, player_id)
    if game is None or player is None:
        return None

    games_df = await load_table_as_dataframe(session, Game)
    player_game_stats_df = await load_table_as_dataframe(session, PlayerGameStats)
    team_game_stats_df = await load_table_as_dataframe(session, TeamGameStats)
    players_df = await load_table_as_dataframe(session, Player)

    if game.status in ("scheduled", "live"):
        features = build_player_game_features(
            games_df, player_game_stats_df, team_game_stats_df, players_df, as_of=game.game_date
        )
    else:
        features = build_player_game_features(
            games_df, player_game_stats_df, team_game_stats_df, players_df
        )

    row = features.loc[(features["game_id"] == game_id) & (features["player_id"] == player_id)]
    if row.empty:
        return None

    # Serve whichever stats have a promoted champion (partial promotion is fine — a stat's model
    # may lag the others). Only when *none* is loaded do we surface the transient 503 below.
    loadable = [stat for stat in stats if model_provider.is_loaded(f"props_{stat}")]
    if not loadable:
        raise RuntimeError(f"no props champion loaded for any of {list(stats)}")

    projections: list[PropsProjection] = []
    for stat in loadable:
        loaded = model_provider.get(f"props_{stat}")
        head = loaded.head
        if not isinstance(head, PropsRegressorHead):
            raise RuntimeError(f"head props_{stat} is not a PropsRegressorHead")
        prediction = head.predict_with_interval(loaded.model, row)
        explanation = humanize(loaded.explain(row))
        if not full:
            explanation = explanation.model_copy(
                update={"contributions": explanation.contributions[:TOP_N_DRIVERS]}
            )
        projections.append(
            PropsProjection(
                player_id=player_id,
                game_id=game_id,
                stat=stat,
                point=float(prediction.point.iloc[0]),
                interval_low=float(prediction.lower.iloc[0]),
                interval_high=float(prediction.upper.iloc[0]),
                explanation=explanation,
            )
        )
    return projections
