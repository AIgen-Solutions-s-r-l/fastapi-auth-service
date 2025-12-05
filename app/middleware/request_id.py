"""Request ID middleware for request tracking and correlation."""

import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable to store request ID for the current request
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


def get_request_id() -> Optional[str]:
    """
    Get the current request ID from context.

    Returns:
        The current request ID or None if not in a request context.
    """
    return request_id_var.get()


def generate_request_id() -> str:
    """
    Generate a new unique request ID.

    Returns:
        A UUID4 string.
    """
    return str(uuid.uuid4())


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds a unique request ID to each request.

    The request ID is:
    - Generated if not provided in the X-Request-ID header
    - Stored in a context variable for access throughout the request lifecycle
    - Added to the response headers as X-Request-ID

    This enables request tracing across services and in logs.
    """

    HEADER_NAME = "X-Request-ID"

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process the request and add request ID tracking."""
        # Check for existing request ID in headers (for distributed tracing)
        request_id = request.headers.get(self.HEADER_NAME)

        # Generate new ID if not provided
        if not request_id:
            request_id = generate_request_id()

        # Store in context variable for use in logging and other places
        token = request_id_var.set(request_id)

        try:
            # Process the request
            response = await call_next(request)

            # Add request ID to response headers
            response.headers[self.HEADER_NAME] = request_id

            return response
        finally:
            # Reset the context variable
            request_id_var.reset(token)


def setup_request_id_middleware(app):
    """
    Setup the request ID middleware on the FastAPI app.

    Args:
        app: The FastAPI application instance.
    """
    app.add_middleware(RequestIDMiddleware)
