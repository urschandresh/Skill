from fastapi import APIRouter

from . import admin, analysts, dashboard, health, leaves, organization, rosters, settings

router = APIRouter()
router.include_router(health.router)
router.include_router(organization.router)
router.include_router(analysts.router)
router.include_router(settings.router)
router.include_router(rosters.router)
router.include_router(leaves.router)
router.include_router(dashboard.router)
router.include_router(admin.router)
