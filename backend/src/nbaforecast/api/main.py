"""FastAPI application factory — backend-api.md Prompt 1.

``/api/v1`` prefix, CORS, a typed ``{error, detail}`` error envelope, OpenAPI docs, and the
resource routers (``games`` has real endpoints as of T2.13; the rest are scaffolded empty per
Prompt 1, filled in by their own tasks). ``/health`` stays unprefixed at the app root — it's an
infra liveness probe (docker-compose's healthcheck already targets it there), not a versioned
business-API concern.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from nbaforecast.api.model_provider import ModelProvider
from nbaforecast.api.routers import games, live, models, players, props, rapm, stats, teams
from nbaforecast.api.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)

# How often the background task re-checks MLflow for a newly promoted champion (§2's "poll
# registry version" hot-reload mechanism).
CHAMPION_POLL_SECONDS = 60.0


async def _poll_for_new_champions(provider: ModelProvider) -> None:
    while True:
        await asyncio.sleep(CHAMPION_POLL_SECONDS)
        await asyncio.to_thread(provider.load_all)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    provider = ModelProvider()
    provider.load_all()  # best-effort — never raises, see ModelProvider.reload()
    app.state.model_provider = provider

    poll_task = asyncio.create_task(_poll_for_new_champions(provider))
    try:
        yield
    finally:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task


app = FastAPI(
    title="NBAforecast",
    description="Explainable NBA predictions, stats hub, and live win probability.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=exc.__class__.__name__, detail=str(exc.detail)).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(error="ValidationError", detail=str(exc.errors())).model_dump(),
    )


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


api_v1 = APIRouter(prefix="/api/v1")
for _router_module in (games, teams, players, props, rapm, stats, live, models):
    api_v1.include_router(_router_module.router)
app.include_router(api_v1)
