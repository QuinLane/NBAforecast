"""Smoke test: the Prefect flows and deployment import and are wired correctly."""

from nbaforecast.ingestion.flows.ingest import backfill_era, backfill_season, ingest_daily


def test_flows_are_named() -> None:
    assert backfill_season.name == "backfill-season"
    assert ingest_daily.name == "ingest-daily"
    assert backfill_era.name == "backfill-era"


def test_backfill_entrypoint_imports() -> None:
    from nbaforecast.entrypoints.backfill import main

    assert callable(main)


def test_deployment_builder_imports() -> None:
    from nbaforecast.ingestion.flows.deployment import build_daily_deployment, serve_ingestion

    assert callable(build_daily_deployment)
    assert callable(serve_ingestion)
