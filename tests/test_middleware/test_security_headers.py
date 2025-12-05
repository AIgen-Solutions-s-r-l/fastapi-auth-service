"""Tests for security headers middleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.security_headers import SecurityHeadersMiddleware


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        app = MagicMock()
        return SecurityHeadersMiddleware(app)

    @pytest.mark.asyncio
    async def test_adds_content_type_options_header(self, middleware):
        """Should add X-Content-Type-Options header."""
        request = MagicMock(spec=Request)
        response = Response(content="test")

        async def call_next(req):
            return response

        result = await middleware.dispatch(request, call_next)

        assert "X-Content-Type-Options" in result.headers
        assert result.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_adds_frame_options_header(self, middleware):
        """Should add X-Frame-Options header."""
        request = MagicMock(spec=Request)
        response = Response(content="test")

        async def call_next(req):
            return response

        result = await middleware.dispatch(request, call_next)

        assert "X-Frame-Options" in result.headers
        assert result.headers["X-Frame-Options"] == "DENY"

    @pytest.mark.asyncio
    async def test_adds_xss_protection_header(self, middleware):
        """Should add X-XSS-Protection header."""
        request = MagicMock(spec=Request)
        response = Response(content="test")

        async def call_next(req):
            return response

        result = await middleware.dispatch(request, call_next)

        assert "X-XSS-Protection" in result.headers
        assert result.headers["X-XSS-Protection"] == "1; mode=block"

    @pytest.mark.asyncio
    async def test_adds_referrer_policy_header(self, middleware):
        """Should add Referrer-Policy header."""
        request = MagicMock(spec=Request)
        response = Response(content="test")

        async def call_next(req):
            return response

        result = await middleware.dispatch(request, call_next)

        assert "Referrer-Policy" in result.headers
        assert result.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_adds_cache_control_headers(self, middleware):
        """Should add cache control headers."""
        request = MagicMock(spec=Request)
        response = Response(content="test")

        async def call_next(req):
            return response

        result = await middleware.dispatch(request, call_next)

        assert "Cache-Control" in result.headers
        assert "no-store" in result.headers["Cache-Control"]
        assert "Pragma" in result.headers
        assert result.headers["Pragma"] == "no-cache"

    @pytest.mark.asyncio
    async def test_adds_permissions_policy_header(self, middleware):
        """Should add Permissions-Policy header."""
        request = MagicMock(spec=Request)
        response = Response(content="test")

        async def call_next(req):
            return response

        result = await middleware.dispatch(request, call_next)

        assert "Permissions-Policy" in result.headers
        policy = result.headers["Permissions-Policy"]
        assert "camera=()" in policy
        assert "microphone=()" in policy
        assert "geolocation=()" in policy

    @pytest.mark.asyncio
    async def test_removes_server_header(self, middleware):
        """Should remove Server header if present."""
        request = MagicMock(spec=Request)
        response = Response(content="test")
        response.headers["Server"] = "MyServer/1.0"

        async def call_next(req):
            return response

        result = await middleware.dispatch(request, call_next)

        assert "Server" not in result.headers

    @pytest.mark.asyncio
    async def test_preserves_response_content(self, middleware):
        """Should preserve the original response content."""
        request = MagicMock(spec=Request)
        response = Response(content="original content", status_code=200)

        async def call_next(req):
            return response

        result = await middleware.dispatch(request, call_next)

        assert result.body == b"original content"
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_all_security_headers_present(self, middleware):
        """Should add all expected security headers."""
        request = MagicMock(spec=Request)
        response = Response(content="test")

        async def call_next(req):
            return response

        result = await middleware.dispatch(request, call_next)

        expected_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Referrer-Policy",
            "Cache-Control",
            "Pragma",
            "Permissions-Policy"
        ]

        for header in expected_headers:
            assert header in result.headers, f"Missing header: {header}"
