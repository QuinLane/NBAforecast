"""Throttled, retry-safe HTTP clients for nba_api and pbpstats."""

from nbaforecast.ingestion.clients.nba_stats import (
    fetch_boxscore,
    fetch_pbp,
    fetch_schedule,
    fetch_shots,
)
from nbaforecast.ingestion.clients.pbp import fetch_possessions
from nbaforecast.ingestion.clients.retrying import retry
from nbaforecast.ingestion.clients.throttle import Throttle, get_throttle

__all__ = [
    "Throttle",
    "fetch_boxscore",
    "fetch_pbp",
    "fetch_possessions",
    "fetch_schedule",
    "fetch_shots",
    "get_throttle",
    "retry",
]
