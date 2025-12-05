"""Tests for request timeout middleware."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.timeout import TimeoutMiddleware


class TestTimeoutMiddleware:
    """Tests for TimeoutMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance with short timeout."""
        app = MagicMock()
        return TimeoutMiddleware(app, timeout_seconds=0.1)

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.method = "GET"
        return request

    @pytest.mark.asyncio
    async def test_passes_request_within_timeout(self, middleware, mock_request):
        """Should return response when request completes within timeout."""
        response = Response(content="success", status_code=200)

        async def call_next(req):
            return response

        with patch('app.middleware.timeout.get_request_id', return_value="req-123"):
            result = await middleware.dispatch(mock_request, call_next)

        assert result.status_code == 200
        assert result.body == b"success"

    @pytest.mark.asyncio
    async def test_returns_504_on_timeout(self, middleware, mock_request):
        """Should return 504 Gateway Timeout when request exceeds timeout."""
        async def slow_call_next(req):
            await asyncio.sleep(1)  # Longer than 0.1s timeout
            return Response(content="success")

        with patch('app.middleware.timeout.get_request_id', return_value="req-123"):
            with patch('app.middleware.timeout.logger'):
                result = await middleware.dispatch(mock_request, slow_call_next)

        assert result.status_code == 504

        import json
        body = json.loads(result.body)
        assert body["error"] == "GatewayTimeout"
        assert body["request_id"] == "req-123"

    @pytest.mark.asyncio
    async def test_logs_timeout_warning(self, middleware, mock_request):
        """Should log warning when request times out."""
        async def slow_call_next(req):
            await asyncio.sleep(1)
            return Response(content="success")

        with patch('app.middleware.timeout.get_request_id', return_value="req-123"):
            with patch('app.middleware.timeout.logger') as mock_logger:
                await middleware.dispatch(mock_request, slow_call_next)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "timeout" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_excludes_healthcheck_paths(self, middleware):
        """Should not apply timeout to healthcheck paths."""
        request = MagicMock(spec=Request)
        request.url.path = "/healthcheck/live"
        request.method = "GET"

        async def slow_call_next(req):
            await asyncio.sleep(0.2)  # Longer than timeout but should pass
            return Response(content="healthy")

        with patch('app.middleware.timeout.get_request_id', return_value="req-123"):
            result = await middleware.dispatch(request, slow_call_next)

        assert result.status_code == 200
        assert result.body == b"healthy"

    @pytest.mark.asyncio
    async def test_excludes_docs_paths(self, middleware):
        """Should not apply timeout to documentation paths."""
        request = MagicMock(spec=Request)
        request.url.path = "/docs"
        request.method = "GET"

        async def slow_call_next(req):
            await asyncio.sleep(0.2)
            return Response(content="docs")

        result = await middleware.dispatch(request, slow_call_next)

        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_excludes_openapi_path(self, middleware):
        """Should not apply timeout to OpenAPI spec path."""
        request = MagicMock(spec=Request)
        request.url.path = "/openapi.json"
        request.method = "GET"

        async def slow_call_next(req):
            await asyncio.sleep(0.2)
            return Response(content="{}")

        result = await middleware.dispatch(request, slow_call_next)

        assert result.status_code == 200


class TestTimeoutMiddlewareConfiguration:
    """Tests for middleware configuration."""

    def test_default_timeout(self):
        """Should use default timeout of 30 seconds."""
        app = MagicMock()
        middleware = TimeoutMiddleware(app)

        assert middleware.timeout_seconds == 30.0

    def test_custom_timeout(self):
        """Should accept custom timeout."""
        app = MagicMock()
        middleware = TimeoutMiddleware(app, timeout_seconds=60.0)

        assert middleware.timeout_seconds == 60.0

    def test_default_exclude_paths(self):
        """Should have default excluded paths."""
        app = MagicMock()
        middleware = TimeoutMiddleware(app)

        assert "/healthcheck" in middleware.exclude_paths
        assert "/docs" in middleware.exclude_paths
        assert "/redoc" in middleware.exclude_paths
        assert "/openapi.json" in middleware.exclude_paths

    def test_custom_exclude_paths(self):
        """Should accept custom excluded paths."""
        app = MagicMock()
        middleware = TimeoutMiddleware(
            app,
            exclude_paths=["/custom", "/paths"]
        )

        assert middleware.exclude_paths == ["/custom", "/paths"]


class TestShouldApplyTimeout:
    """Tests for _should_apply_timeout method."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        app = MagicMock()
        return TimeoutMiddleware(app)

    def test_applies_to_api_paths(self, middleware):
        """Should apply timeout to normal API paths."""
        assert middleware._should_apply_timeout("/api/users") is True
        assert middleware._should_apply_timeout("/v1/auth/login") is True
        assert middleware._should_apply_timeout("/credits/balance") is True

    def test_excludes_healthcheck_paths(self, middleware):
        """Should not apply to healthcheck paths."""
        assert middleware._should_apply_timeout("/healthcheck") is False
        assert middleware._should_apply_timeout("/healthcheck/live") is False
        assert middleware._should_apply_timeout("/healthcheck/ready") is False

    def test_excludes_documentation_paths(self, middleware):
        """Should not apply to documentation paths."""
        assert middleware._should_apply_timeout("/docs") is False
        assert middleware._should_apply_timeout("/redoc") is False
        assert middleware._should_apply_timeout("/openapi.json") is False
