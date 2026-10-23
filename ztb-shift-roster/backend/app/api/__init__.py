from fastapi import APIRouter

from . import analysts, health, organization, settings

router = APIRouter()
router.include_router(health.router)
router.include_router(organization.router)
router.include_router(analysts.router)
router.include_router(settings.router)
