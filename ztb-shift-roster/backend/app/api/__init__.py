from fastapi import APIRouter

from . import analysts, health, organization, rosters, settings

router = APIRouter()
router.include_router(health.router)
router.include_router(organization.router)
router.include_router(analysts.router)
router.include_router(settings.router)
router.include_router(rosters.router)
