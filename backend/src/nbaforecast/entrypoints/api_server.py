"""Entry point for the FastAPI development server."""

import uvicorn

from nbaforecast.config.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "nbaforecast.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.env == "development",
        log_level=settings.log_level.lower(),
    )
