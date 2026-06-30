"""Props router — backend-api.md §3 (scaffolded T2.13, real endpoints land with their own tasks)."""

from fastapi import APIRouter

router = APIRouter(prefix="/props", tags=["props"])
