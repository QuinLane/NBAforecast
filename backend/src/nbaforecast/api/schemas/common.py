"""Shared response envelopes — backend-api.md §4 + §6."""

from pydantic import BaseModel


class Page[T](BaseModel):
    """Uniform pagination envelope every list endpoint returns."""

    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    """The typed error envelope every non-2xx response returns (backend-api.md §6)."""

    error: str
    detail: str
