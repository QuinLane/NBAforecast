"""Project-wide exception hierarchy (engineering-standards.md §2).

Everything raised by NBAforecast library code descends from :class:`NbaForecastError` so
callers can catch the whole family, and pipelines fail loudly instead of swallowing errors.
"""


class NbaForecastError(Exception):
    """Base class for all NBAforecast errors."""


class IngestionError(NbaForecastError):
    """Raised when pulling/landing data from an external source fails."""


class TransientIngestionError(IngestionError):
    """A retryable ingestion failure (timeout, connection drop, transient 5xx)."""


class RateLimitError(TransientIngestionError):
    """The upstream API rate-limited us (HTTP 429). Retryable with backoff."""


class DataValidationError(NbaForecastError):
    """Raised when parsed data fails its Pandera schema (T1.4)."""
