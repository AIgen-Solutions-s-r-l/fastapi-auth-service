"""Tests for error handlers."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.error_handlers import (
    _build_error_response,
    validation_exception_handler,
    http_exception_handler,
    sqlalchemy_exception_handler,
    generic_exception_handler
)


class TestBuildErrorResponse:
    """Tests for _build_error_response helper function."""

    def test_basic_error_response(self):
        """Should build response with error and message."""
        with patch('app.core.error_handlers.get_request_id', return_value=None):
            response = _build_error_response(
                error="TestError",
                message="Test message",
                status_code=400
            )

        assert response["error"] == "TestError"
        assert response["message"] == "Test message"
        assert "request_id" not in response

    def test_includes_request_id_when_available(self):
        """Should include request_id when available."""
        with patch('app.core.error_handlers.get_request_id', return_value="test-request-id-123"):
            response = _build_error_response(
                error="TestError",
                message="Test message",
                status_code=400
            )

        assert response["request_id"] == "test-request-id-123"

    def test_excludes_request_id_when_disabled(self):
        """Should not include request_id when disabled."""
        with patch('app.core.error_handlers.get_request_id', return_value="test-id"):
            response = _build_error_response(
                error="TestError",
                message="Test message",
                status_code=400,
                include_request_id=False
            )

        assert "request_id" not in response

    def test_includes_details_when_provided(self):
        """Should include details when provided."""
        with patch('app.core.error_handlers.get_request_id', return_value=None):
            details = [{"loc": ["body", "email"], "msg": "invalid"}]
            response = _build_error_response(
                error="ValidationError",
                message="Invalid data",
                status_code=422,
                details=details
            )

        assert response["details"] == details

    def test_excludes_details_when_none(self):
        """Should not include details when None."""
        with patch('app.core.error_handlers.get_request_id', return_value=None):
            response = _build_error_response(
                error="TestError",
                message="Test message",
                status_code=400,
                details=None
            )

        assert "details" not in response


class TestValidationExceptionHandler:
    """Tests for validation_exception_handler."""

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = MagicMock()
        request.url = "http://test.com/api/test"
        request.method = "POST"
        return request

    @pytest.mark.asyncio
    async def test_returns_422_status(self, mock_request):
        """Should return 422 status code."""
        exc = MagicMock(spec=RequestValidationError)
        exc.errors.return_value = [{"loc": ["body", "email"], "msg": "required"}]

        with patch('app.core.error_handlers.get_request_id', return_value="req-123"):
            with patch('app.core.error_handlers.logger'):
                response = await validation_exception_handler(mock_request, exc)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_includes_validation_errors(self, mock_request):
        """Should include validation errors in response."""
        errors = [{"loc": ["body", "email"], "msg": "required", "type": "value_error"}]
        exc = MagicMock(spec=RequestValidationError)
        exc.errors.return_value = errors

        with patch('app.core.error_handlers.get_request_id', return_value="req-123"):
            with patch('app.core.error_handlers.logger'):
                response = await validation_exception_handler(mock_request, exc)

        import json
        body = json.loads(response.body)
        assert body["error"] == "ValidationError"
        assert body["details"] == errors


class TestHttpExceptionHandler:
    """Tests for http_exception_handler."""

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = MagicMock()
        request.url = "http://test.com/api/test"
        request.method = "GET"
        return request

    @pytest.mark.asyncio
    async def test_returns_correct_status_code(self, mock_request):
        """Should return the same status code as exception."""
        exc = HTTPException(status_code=404, detail="Not found")

        with patch('app.core.error_handlers.get_request_id', return_value="req-123"):
            with patch('app.core.error_handlers.logger'):
                response = await http_exception_handler(mock_request, exc)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_maps_status_to_error_type(self, mock_request):
        """Should map status codes to appropriate error types."""
        test_cases = [
            (400, "BadRequest"),
            (401, "Unauthorized"),
            (403, "Forbidden"),
            (404, "NotFound"),
            (429, "RateLimitExceeded"),
        ]

        for status_code, expected_error in test_cases:
            exc = HTTPException(status_code=status_code, detail="Test")

            with patch('app.core.error_handlers.get_request_id', return_value="req-123"):
                with patch('app.core.error_handlers.logger'):
                    response = await http_exception_handler(mock_request, exc)

            import json
            body = json.loads(response.body)
            assert body["error"] == expected_error, f"Failed for status {status_code}"

    @pytest.mark.asyncio
    async def test_preserves_dict_detail_with_message(self, mock_request):
        """Should preserve dict detail if it has message key."""
        detail = {"message": "Custom message", "code": "CUSTOM_ERROR"}
        exc = HTTPException(status_code=400, detail=detail)

        with patch('app.core.error_handlers.get_request_id', return_value="req-123"):
            with patch('app.core.error_handlers.logger'):
                response = await http_exception_handler(mock_request, exc)

        import json
        body = json.loads(response.body)
        assert body["message"] == "Custom message"
        assert body["code"] == "CUSTOM_ERROR"
        assert body["request_id"] == "req-123"


class TestSqlalchemyExceptionHandler:
    """Tests for sqlalchemy_exception_handler."""

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = MagicMock()
        request.url = "http://test.com/api/test"
        request.method = "POST"
        return request

    @pytest.mark.asyncio
    async def test_returns_500_status(self, mock_request):
        """Should return 500 status code."""
        from sqlalchemy.exc import SQLAlchemyError
        exc = SQLAlchemyError("Database error")

        with patch('app.core.error_handlers.get_request_id', return_value="req-123"):
            with patch('app.core.error_handlers.logger'):
                response = await sqlalchemy_exception_handler(mock_request, exc)

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_returns_generic_database_error_message(self, mock_request):
        """Should not expose internal database error details."""
        from sqlalchemy.exc import SQLAlchemyError
        exc = SQLAlchemyError("Sensitive database error information")

        with patch('app.core.error_handlers.get_request_id', return_value="req-123"):
            with patch('app.core.error_handlers.logger'):
                response = await sqlalchemy_exception_handler(mock_request, exc)

        import json
        body = json.loads(response.body)
        assert body["error"] == "DatabaseError"
        assert "Sensitive" not in body["message"]
        assert "Please try again later" in body["message"]


class TestGenericExceptionHandler:
    """Tests for generic_exception_handler."""

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = MagicMock()
        request.url = "http://test.com/api/test"
        request.method = "GET"
        return request

    @pytest.mark.asyncio
    async def test_returns_500_status(self, mock_request):
        """Should return 500 status code."""
        exc = Exception("Unexpected error")

        with patch('app.core.error_handlers.get_request_id', return_value="req-123"):
            with patch('app.core.error_handlers.logger'):
                response = await generic_exception_handler(mock_request, exc)

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_returns_generic_error_message(self, mock_request):
        """Should not expose internal error details."""
        exc = Exception("Internal sensitive information")

        with patch('app.core.error_handlers.get_request_id', return_value="req-123"):
            with patch('app.core.error_handlers.logger'):
                response = await generic_exception_handler(mock_request, exc)

        import json
        body = json.loads(response.body)
        assert body["error"] == "InternalServerError"
        assert "sensitive" not in body["message"].lower()
        assert body["request_id"] == "req-123"
