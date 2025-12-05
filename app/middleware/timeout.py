"""Request timeout middleware for preventing long-running requests."""

import asyncio
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.log.logging import logger
from app.middleware.request_id import get_request_id


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces request timeout limits.

    This middleware prevents requests from running indefinitely by setting
    a maximum execution time. If a request exceeds the timeout, a 504
    Gateway Timeout response is returned.

    Attributes:
        timeout_seconds: Maximum time allowed for request processing
        exclude_paths: List of paths to exclude from timeout enforcement
    """

    def __init__(
        self,
        app,
        timeout_seconds: float = 30.0,
        exclude_paths: Optional[list] = None
    ):
        """
        Initialize the timeout middleware.

        Args:
            app: The ASGI application
            timeout_seconds: Maximum request processing time in seconds
            exclude_paths: List of path prefixes to exclude from timeout
        """
        super().__init__(app)
        self.timeout_seconds = timeout_seconds
        self.exclude_paths = exclude_paths or [
            "/healthcheck",  # Health checks should not timeout
            "/docs",         # Swagger UI
            "/redoc",        # ReDoc
            "/openapi.json", # OpenAPI spec
        ]

    def _should_apply_timeout(self, path: str) -> bool:
        """Check if timeout should be applied to this request path."""
        for excluded in self.exclude_paths:
            if path.startswith(excluded):
                return False
        return True

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process the request with timeout enforcement."""
        # Skip timeout for excluded paths
        if not self._should_apply_timeout(request.url.path):
            return await call_next(request)

        request_id = get_request_id()

        try:
            # Wrap the request processing in a timeout
            response = await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout_seconds
            )
            return response

        except asyncio.TimeoutError:
            logger.warning(
                f"Request timeout after {self.timeout_seconds}s",
                event_type="request_timeout",
                path=str(request.url.path),
                method=request.method,
                timeout_seconds=self.timeout_seconds,
                request_id=request_id
            )

            return JSONResponse(
                status_code=504,
                content={
                    "error": "GatewayTimeout",
                    "message": f"Request processing exceeded {self.timeout_seconds} seconds",
                    "request_id": request_id
                }
            )


def setup_timeout_middleware(
    app,
    timeout_seconds: float = 30.0,
    exclude_paths: Optional[list] = None
):
    """
    Setup the timeout middleware on the FastAPI app.

    Args:
        app: The FastAPI application instance
        timeout_seconds: Maximum request processing time in seconds
        exclude_paths: List of path prefixes to exclude from timeout
    """
    app.add_middleware(
        TimeoutMiddleware,
        timeout_seconds=timeout_seconds,
        exclude_paths=exclude_paths
    )
