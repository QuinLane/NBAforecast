"""Entrypoint for the Prefect worker: serve the scheduled ingestion deployment."""

import logging

from nbaforecast.config.settings import get_settings
from nbaforecast.ingestion.flows.deployment import serve_ingestion


def main() -> None:
    """Configure logging and serve the nightly ingestion deployment (blocks)."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    serve_ingestion()


if __name__ == "__main__":
    main()
