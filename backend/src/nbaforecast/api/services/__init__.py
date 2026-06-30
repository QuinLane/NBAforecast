"""Business logic between routers and storage/models — keeps routers thin (backend-api.md §1)."""

from nbaforecast.api.services import games

__all__ = ["games"]
