"""Model-metadata service — champion provenance from the MLflow registry (backend-api.md §3)."""

from datetime import UTC, datetime

from nbaforecast.api.schemas.models import ChampionProvenance
from nbaforecast.models.heads import HEAD_REGISTRY
from nbaforecast.training import registry


def _format_season(train_seasons: str | None) -> str | None:
    """Latest trained season as ``YYYY-YY`` from the comma-joined ``train_seasons`` param."""
    if not train_seasons:
        return None
    years = [part for part in train_seasons.split(",") if part.strip().isdigit()]
    if not years:
        return None
    start = int(years[-1])
    return f"{start}-{(start + 1) % 100:02d}"


def champion_provenance() -> list[ChampionProvenance]:
    """Provenance for every head that has a promoted champion (skips heads without one).

    Blocking MLflow calls — call from a thread (``asyncio.to_thread``) in the async router.
    """
    provenance: list[ChampionProvenance] = []
    for head_name in HEAD_REGISTRY:
        run = registry.get_champion_run(head_name)
        if run is None:
            continue
        params = run.data.params
        started_ms = run.info.start_time
        provenance.append(
            ChampionProvenance(
                head=head_name,
                version=run.info.run_id[:8],
                feature_version=params.get("feature_version"),
                trained_through_season=_format_season(params.get("train_seasons")),
                trained_at=(
                    datetime.fromtimestamp(started_ms / 1000, tz=UTC)
                    if started_ms is not None
                    else None
                ),
            )
        )
    return provenance
