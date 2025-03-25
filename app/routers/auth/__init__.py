"""Authentication package.

This package contains all authentication-related routers and endpoints.
The main router is exported for inclusion in the FastAPI app.
"""

from app.routers.auth.auth_router import router

__all__ = ["router"]