"""Security headers middleware for enhanced protection."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    These headers help protect against common web vulnerabilities:
    - XSS attacks
    - Clickjacking
    - MIME type sniffing
    - Information disclosure
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Add security headers to the response."""
        response = await call_next(request)

        # Prevent XSS attacks by controlling how content is loaded
        # Note: adjust CSP based on your frontend requirements
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking by disallowing framing
        response.headers["X-Frame-Options"] = "DENY"

        # Enable browser XSS protection (legacy, but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Prevent caching of sensitive data
        # Note: may need adjustment for static assets
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"

        # Remove server identification header if present
        if "Server" in response.headers:
            del response.headers["Server"]

        # Permissions Policy (formerly Feature-Policy)
        # Restrict access to browser features
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )

        return response


def setup_security_headers(app):
    """
    Setup the security headers middleware on the FastAPI app.

    Args:
        app: The FastAPI application instance.
    """
    app.add_middleware(SecurityHeadersMiddleware)
