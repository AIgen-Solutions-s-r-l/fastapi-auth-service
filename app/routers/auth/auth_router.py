"""Main authentication router that aggregates all auth-related endpoints."""

from fastapi import APIRouter
from app.routers.auth.user_auth import router as user_auth_router
from app.routers.auth.email_verification import router as email_verification_router
from app.routers.auth.password_management import router as password_management_router
from app.routers.auth.email_management import router as email_management_router
from app.routers.auth.social_auth import router as social_auth_router
from app.routers.auth.auth_utils import router as auth_utils_router
from app.routers.auth.user_profile import router as user_profile_router

# Create main router with the same tags as the original auth_router.py
router = APIRouter(tags=["authentication"])

# Include all auth-related routers without path prefix to maintain existing routes
router.include_router(user_auth_router)
router.include_router(email_verification_router)
router.include_router(password_management_router)
router.include_router(email_management_router)
router.include_router(social_auth_router)
router.include_router(auth_utils_router)
router.include_router(user_profile_router)