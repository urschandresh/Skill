from fastapi import APIRouter

from . import health

router = APIRouter()
router.include_router(health.router)
