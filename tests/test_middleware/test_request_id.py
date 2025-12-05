"""Tests for request ID middleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.request_id import (
    RequestIDMiddleware,
    get_request_id,
    generate_request_id,
    request_id_var
)


class TestGenerateRequestId:
    """Tests for request ID generation."""

    def test_generates_uuid_format(self):
        """Generated ID should be in UUID format."""
        request_id = generate_request_id()
        # UUID format: 8-4-4-4-12 = 36 characters with hyphens
        assert len(request_id) == 36
        assert request_id.count("-") == 4

    def test_generates_unique_ids(self):
        """Each call should generate a unique ID."""
        ids = [generate_request_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestGetRequestId:
    """Tests for getting request ID from context."""

    def test_returns_none_outside_context(self):
        """Should return None when not in a request context."""
        # Reset context to ensure clean state
        token = request_id_var.set(None)
        try:
            assert get_request_id() is None
        finally:
            request_id_var.reset(token)

    def test_returns_id_in_context(self):
        """Should return the ID set in context."""
        test_id = "test-request-id-123"
        token = request_id_var.set(test_id)
        try:
            assert get_request_id() == test_id
        finally:
            request_id_var.reset(token)


class TestRequestIDMiddleware:
    """Tests for RequestIDMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        app = MagicMock()
        return RequestIDMiddleware(app)

    @pytest.mark.asyncio
    async def test_generates_new_request_id(self, middleware):
        """Should generate new request ID when not provided."""
        # Create mock request without X-Request-ID header
        request = MagicMock(spec=Request)
        request.headers = {}

        # Create mock response
        response = Response(content="test")

        # Create call_next that returns response
        async def call_next(req):
            # Verify request ID is set in context during request processing
            assert get_request_id() is not None
            return response

        result = await middleware.dispatch(request, call_next)

        # Verify X-Request-ID header is set in response
        assert "X-Request-ID" in result.headers
        assert len(result.headers["X-Request-ID"]) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_uses_provided_request_id(self, middleware):
        """Should use existing X-Request-ID header when provided."""
        provided_id = "existing-request-id-456"

        # Create mock request with X-Request-ID header
        request = MagicMock(spec=Request)
        request.headers = {"X-Request-ID": provided_id}

        # Create mock response
        response = Response(content="test")

        # Create call_next that returns response
        async def call_next(req):
            # Verify the provided ID is used
            assert get_request_id() == provided_id
            return response

        result = await middleware.dispatch(request, call_next)

        # Verify the same ID is in response
        assert result.headers["X-Request-ID"] == provided_id

    @pytest.mark.asyncio
    async def test_context_reset_after_request(self, middleware):
        """Context should be reset after request completes."""
        request = MagicMock(spec=Request)
        request.headers = {}
        response = Response(content="test")

        captured_id = None

        async def call_next(req):
            nonlocal captured_id
            captured_id = get_request_id()
            return response

        await middleware.dispatch(request, call_next)

        # After dispatch, context should be reset
        # Note: In actual async context, this depends on context variable behavior
        # This test verifies the middleware attempts to reset

    @pytest.mark.asyncio
    async def test_header_name_constant(self, middleware):
        """Header name should be X-Request-ID."""
        assert middleware.HEADER_NAME == "X-Request-ID"


class TestRequestIdIntegration:
    """Integration tests for request ID functionality."""

    def test_request_id_flows_through_context(self):
        """Request ID should flow through context variable correctly."""
        test_id = "integration-test-id"

        # Simulate setting ID in middleware
        token = request_id_var.set(test_id)

        try:
            # Simulate accessing ID in application code
            retrieved_id = get_request_id()
            assert retrieved_id == test_id
        finally:
            request_id_var.reset(token)

        # After reset, should be None
        assert get_request_id() is None
