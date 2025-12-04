"""Rate limiting middleware using SlowAPI."""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request, FastAPI
from starlette.responses import JSONResponse

from app.core.config import settings
from app.log.logging import logger


def get_request_identifier(request: Request) -> str:
    """
    Get a unique identifier for rate limiting.

    Uses X-API-Key header for internal services (bypasses rate limit),
    otherwise uses client IP address.
    """
    # Check for internal API key - bypass rate limiting for internal services
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key == settings.INTERNAL_API_KEY:
        # Return a special identifier that won't hit limits
        return "internal-service-bypass"

    # For regular requests, use IP address
    return get_remote_address(request)


# Initialize limiter with configuration
limiter = Limiter(
    key_func=get_request_identifier,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    enabled=settings.RATE_LIMIT_ENABLED,
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler for rate limit exceeded errors."""
    logger.warning(
        "Rate limit exceeded",
        event_type="rate_limit_exceeded",
        client_ip=get_remote_address(request),
        path=request.url.path,
        limit=str(exc.detail),
    )

    # Extract retry-after from the exception if available
    retry_after = getattr(exc, "retry_after", 60)

    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please slow down.",
                "retry_after": retry_after,
            }
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(exc.detail) if exc.detail else "unknown",
        }
    )


def setup_rate_limiting(app: FastAPI) -> None:
    """Configure rate limiting for the FastAPI application."""
    if not settings.RATE_LIMIT_ENABLED:
        logger.info("Rate limiting is disabled")
        return

    # Add limiter to app state
    app.state.limiter = limiter

    # Add exception handler
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Add middleware
    app.add_middleware(SlowAPIMiddleware)

    logger.info(
        "Rate limiting configured",
        event_type="rate_limit_configured",
        default_limit=settings.RATE_LIMIT_DEFAULT,
        auth_limit=settings.RATE_LIMIT_AUTH,
        storage=settings.RATE_LIMIT_STORAGE_URI,
    )
