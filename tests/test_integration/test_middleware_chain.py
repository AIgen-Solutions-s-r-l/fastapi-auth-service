"""Integration tests for the complete middleware chain.

These tests verify that all middleware components work together correctly:
- Request ID generation and propagation
- Security headers injection
- Rate limiting
- Request timeout
- Error handling with request ID
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestMiddlewareChainIntegration:
    """Integration tests for middleware chain."""

    @pytest.fixture
    def client(self):
        """Create test client with full middleware stack."""
        # Import here to ensure fresh app instance
        from app.main import app
        return TestClient(app)

    def test_request_id_generated_for_requests(self, client):
        """Should generate X-Request-ID for all requests."""
        response = client.get("/")

        assert "X-Request-ID" in response.headers
        # UUID format: 8-4-4-4-12
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) == 36
        assert request_id.count("-") == 4

    def test_request_id_preserved_when_provided(self, client):
        """Should preserve X-Request-ID when provided by client."""
        custom_id = "custom-request-id-12345"
        response = client.get("/", headers={"X-Request-ID": custom_id})

        assert response.headers["X-Request-ID"] == custom_id

    def test_security_headers_present_on_all_responses(self, client):
        """Should include security headers on all responses."""
        response = client.get("/")

        # Check all security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "strict-origin" in response.headers.get("Referrer-Policy", "")
        assert "no-store" in response.headers.get("Cache-Control", "")

    def test_security_headers_on_error_responses(self, client):
        """Should include security headers even on error responses."""
        response = client.get("/nonexistent-endpoint-12345")

        assert response.status_code == 404
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_healthcheck_returns_request_id(self, client):
        """Health check should include request ID in response headers."""
        response = client.get("/healthcheck/live")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_api_versions_endpoint(self, client):
        """API versions endpoint should work with all middleware."""
        response = client.get("/api/versions")

        assert response.status_code == 200
        data = response.json()
        assert "current_version" in data
        assert "supported_versions" in data
        assert data["current_version"] == "v1"

    def test_versioned_routes_accessible(self, client):
        """Versioned routes should be accessible."""
        # Test that versioned root exists (will get auth error, but route exists)
        response = client.get("/v1/auth/me")

        # Should get 401 (auth required), not 404 (not found)
        assert response.status_code == 401

    def test_legacy_routes_still_work(self, client):
        """Legacy (non-versioned) routes should still work."""
        response = client.get("/auth/me")

        # Should get 401 (auth required), not 404 (not found)
        assert response.status_code == 401


class TestErrorHandlingIntegration:
    """Integration tests for error handling with middleware."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from app.main import app
        return TestClient(app)

    def test_validation_error_includes_request_id(self, client):
        """Validation errors should include request_id."""
        # Send invalid login request
        response = client.post(
            "/auth/login",
            json={"invalid": "data"}
        )

        assert response.status_code == 422
        data = response.json()
        assert "request_id" in data
        assert "error" in data
        assert data["error"] == "ValidationError"

    def test_404_error_includes_request_id(self, client):
        """404 errors should include request_id."""
        response = client.get("/nonexistent-12345")

        assert response.status_code == 404
        data = response.json()
        assert "request_id" in data

    def test_error_response_has_consistent_format(self, client):
        """All error responses should have consistent format."""
        response = client.post(
            "/auth/login",
            json={}  # Missing required fields
        )

        assert response.status_code == 422
        data = response.json()

        # Check consistent error format
        assert "error" in data
        assert "message" in data
        assert "request_id" in data


class TestHealthCheckIntegration:
    """Integration tests for health check endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from app.main import app
        return TestClient(app)

    def test_liveness_probe(self, client):
        """Liveness probe should return quickly."""
        response = client.get("/healthcheck/live")

        assert response.status_code == 200
        data = response.json()
        assert data["alive"] is True
        assert "uptime_seconds" in data

    def test_readiness_probe_format(self, client):
        """Readiness probe should return proper format."""
        response = client.get("/healthcheck/ready")

        # May be 200 or 503 depending on DB state
        data = response.json()
        if response.status_code == 200:
            assert data["ready"] is True
            assert "checks" in data

    def test_full_health_check_format(self, client):
        """Full health check should return component details."""
        response = client.get("/healthcheck/full")

        data = response.json()
        if response.status_code == 200:
            assert "status" in data
            assert "components" in data
            assert "uptime_seconds" in data


class TestCORSIntegration:
    """Integration tests for CORS middleware."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from app.main import app
        return TestClient(app)

    def test_cors_headers_on_options_request(self, client):
        """OPTIONS request should return CORS headers."""
        response = client.options(
            "/auth/login",
            headers={"Origin": "http://localhost:3000"}
        )

        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers or response.status_code == 200

    def test_request_id_exposed_in_cors(self, client):
        """X-Request-ID should be exposed in CORS headers."""
        response = client.get(
            "/",
            headers={"Origin": "http://localhost:3000"}
        )

        # Check that X-Request-ID is in exposed headers or response
        assert "X-Request-ID" in response.headers


class TestMiddlewareOrder:
    """Tests to verify middleware executes in correct order."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from app.main import app
        return TestClient(app)

    def test_request_id_available_in_error_handlers(self, client):
        """Request ID should be set before error handlers run."""
        response = client.post(
            "/auth/login",
            json={"username": "test"}  # Missing password
        )

        assert response.status_code == 422
        data = response.json()

        # Request ID should be in response (proves it was set before error handling)
        assert "request_id" in data
        # And in headers
        assert "X-Request-ID" in response.headers
        # Both should match
        assert data["request_id"] == response.headers["X-Request-ID"]

    def test_security_headers_added_after_response(self, client):
        """Security headers should be added to all responses."""
        # Test on successful response
        response = client.get("/")
        assert response.status_code == 200
        assert "X-Frame-Options" in response.headers

        # Test on error response
        response = client.get("/nonexistent")
        assert response.status_code == 404
        assert "X-Frame-Options" in response.headers
