"""API versioning support for the authentication service.

This module provides utilities for API versioning using URL path prefixes.
The versioning strategy allows for backward compatibility while enabling
gradual API evolution.

Usage:
    # In main.py:
    from app.core.versioning import create_versioned_app, APIVersion

    # Include versioned routers
    app.include_router(auth_router, prefix=f"/{APIVersion.V1}/auth")

    # Or use the helper
    include_versioned_router(app, auth_router, "auth", [APIVersion.V1])
"""

from enum import Enum
from typing import List, Optional, Callable
from fastapi import APIRouter, FastAPI, Header, HTTPException
from functools import wraps

from app.log.logging import logger


class APIVersion(str, Enum):
    """Supported API versions.

    Version History:
    - V1 (1.0): Initial stable API release
    """
    V1 = "v1"

    @classmethod
    def latest(cls) -> "APIVersion":
        """Get the latest API version."""
        return cls.V1

    @classmethod
    def supported(cls) -> List["APIVersion"]:
        """Get all supported API versions."""
        return list(cls)

    @classmethod
    def is_supported(cls, version: str) -> bool:
        """Check if a version string is supported."""
        try:
            cls(version)
            return True
        except ValueError:
            return False


# Header name for API version (optional, for clients that prefer header-based versioning)
API_VERSION_HEADER = "X-API-Version"


def get_api_version_from_header(
    x_api_version: Optional[str] = Header(None, alias=API_VERSION_HEADER)
) -> Optional[APIVersion]:
    """
    Extract API version from request header (optional versioning method).

    This is an alternative to URL-based versioning for clients that prefer
    header-based version selection.

    Args:
        x_api_version: The X-API-Version header value

    Returns:
        The APIVersion enum value or None if not specified
    """
    if x_api_version is None:
        return None

    if not APIVersion.is_supported(x_api_version):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "UnsupportedAPIVersion",
                "message": f"API version '{x_api_version}' is not supported",
                "supported_versions": [v.value for v in APIVersion.supported()]
            }
        )

    return APIVersion(x_api_version)


def include_versioned_router(
    app: FastAPI,
    router: APIRouter,
    prefix: str,
    versions: Optional[List[APIVersion]] = None,
    **kwargs
) -> None:
    """
    Include a router with version prefixes.

    This helper function includes a router multiple times with different
    version prefixes, allowing the same endpoints to be accessible under
    multiple API versions.

    Args:
        app: The FastAPI application
        router: The router to include
        prefix: The base prefix (e.g., "auth")
        versions: List of versions to include (defaults to all supported)
        **kwargs: Additional arguments passed to include_router

    Example:
        include_versioned_router(app, auth_router, "auth", [APIVersion.V1])
        # Creates routes: /v1/auth/...
    """
    if versions is None:
        versions = APIVersion.supported()

    for version in versions:
        versioned_prefix = f"/{version.value}/{prefix.lstrip('/')}"
        app.include_router(router, prefix=versioned_prefix, **kwargs)
        logger.debug(
            f"Registered versioned router",
            event_type="router_registered",
            version=version.value,
            prefix=versioned_prefix
        )


def deprecated_endpoint(
    deprecation_version: APIVersion,
    removal_version: Optional[APIVersion] = None,
    alternative: Optional[str] = None
) -> Callable:
    """
    Decorator to mark an endpoint as deprecated.

    Adds deprecation headers to the response and logs usage of deprecated endpoints.

    Args:
        deprecation_version: The version where this endpoint was deprecated
        removal_version: The version where this endpoint will be removed (optional)
        alternative: The alternative endpoint to use (optional)

    Example:
        @router.get("/old-endpoint")
        @deprecated_endpoint(APIVersion.V1, alternative="/new-endpoint")
        async def old_endpoint():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Log deprecated endpoint usage
            logger.warning(
                f"Deprecated endpoint accessed: {func.__name__}",
                event_type="deprecated_endpoint_access",
                endpoint=func.__name__,
                deprecation_version=deprecation_version.value,
                removal_version=removal_version.value if removal_version else None,
                alternative=alternative
            )

            # Call the original function
            response = await func(*args, **kwargs)

            # Note: For full header support, the endpoint should return a Response object
            # or use a response_class parameter
            return response

        # Add deprecation info to function metadata for documentation
        wrapper.__deprecated__ = True
        wrapper.__deprecation_version__ = deprecation_version
        wrapper.__removal_version__ = removal_version
        wrapper.__alternative__ = alternative

        return wrapper
    return decorator


# Version info for OpenAPI documentation
VERSION_INFO = {
    APIVersion.V1: {
        "title": "API v1",
        "description": "Initial stable API version",
        "status": "stable"
    }
}


def get_version_info(version: APIVersion) -> dict:
    """Get information about a specific API version."""
    return VERSION_INFO.get(version, {"status": "unknown"})
