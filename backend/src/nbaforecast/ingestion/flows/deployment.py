"""Prefect deployment wiring the nightly ``ingest_daily`` schedule (data-pipeline.md Prompt 4)."""

import logging
from typing import cast

from prefect import serve
from prefect.deployments.runner import RunnerDeployment
from prefect.schedules import Cron

from nbaforecast.config.settings import get_settings
from nbaforecast.ingestion.flows.ingest import ingest_daily

logger = logging.getLogger(__name__)


def build_daily_deployment() -> RunnerDeployment:
    """Build the nightly ``ingest_daily`` deployment from the configured cron + timezone."""
    settings = get_settings()
    # to_deployment is sync for a flow but typed as a sync/async union; this flow path is sync.
    return cast(
        "RunnerDeployment",
        ingest_daily.to_deployment(
            name="ingest-daily-nightly",
            schedule=Cron(settings.ingest_daily_cron, timezone=settings.ingest_timezone),
        ),
    )


def serve_ingestion() -> None:
    """Serve the nightly ingestion deployment (blocks; the Prefect worker entrypoint)."""
    settings = get_settings()
    logger.info(
        "serving ingest-daily on cron %r (%s)",
        settings.ingest_daily_cron,
        settings.ingest_timezone,
    )
    serve(build_daily_deployment())
