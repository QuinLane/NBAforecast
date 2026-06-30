"""CLI entrypoint to run the full-era (or a bounded) historical backfill (roadmap M1 / T1.7).

Examples:
    nbaforecast-backfill                         # full PBP era, 1996-97 → present
    nbaforecast-backfill --start-year 2023       # 2023-24 → present
    nbaforecast-backfill --start-year 2023 --end-year 2023 --season-type "Regular Season"

Prerequisites: the local stack is up (``docker compose up``) and migrations are applied
(``alembic upgrade head``). The run is resumable — re-running continues from the checkpoint.
"""

import argparse
import asyncio
import logging

from nbaforecast.config.settings import get_settings
from nbaforecast.ingestion.flows.ingest import (
    ERA_SEASON_TYPES,
    PBP_ERA_START_YEAR,
    backfill_era,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill NBA seasons into bronze + silver.")
    parser.add_argument("--start-year", type=int, default=PBP_ERA_START_YEAR)
    parser.add_argument(
        "--end-year", type=int, default=None, help="Defaults to the current season."
    )
    parser.add_argument(
        "--season-type",
        action="append",
        dest="season_types",
        choices=["Regular Season", "Playoffs", "Pre Season", "Play In"],
        help="Repeatable; defaults to Regular Season + Playoffs.",
    )
    return parser.parse_args()


def main() -> None:
    """Parse args and run the era backfill flow to completion."""
    args = _parse_args()
    logging.basicConfig(level=get_settings().log_level)
    season_types = tuple(args.season_types) if args.season_types else ERA_SEASON_TYPES
    processed = asyncio.run(
        backfill_era(
            start_year=args.start_year,
            end_year=args.end_year,
            season_types=season_types,
        )
    )
    logging.getLogger(__name__).info("backfill complete: %d games processed", processed)


if __name__ == "__main__":
    main()
