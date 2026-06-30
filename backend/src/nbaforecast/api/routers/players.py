"""Players router — backend-api.md §3 (scaffolded in T2.13; real endpoints land later)."""

from fastapi import APIRouter

router = APIRouter(prefix="/players", tags=["players"])
