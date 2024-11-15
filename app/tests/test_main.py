# tests/test_main.py
import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from httpx import AsyncClient
from typing import Generator

from app.main import app
from app.core.exceptions import AuthException, UserAlreadyExistsError


# Fixture per il client di test
@pytest.fixture
async def async_client() -> Generator:
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
class TestMainApplication:
    """Test suite for main FastAPI application configuration and endpoints."""

    async def test_root_endpoint(self, async_client: AsyncClient):
        """Test the root endpoint returns correct status and message."""
        response = await async_client.get("/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "authService is up and running!"}

    async def test_app_title_and_description(self):
        """Test the application metadata is correctly configured."""
        assert app.title == "Auth Service API"
        assert app.description == "Authentication service"
        assert app.version == "1.0.0"

    async def test_cors_middleware_headers(self, async_client: AsyncClient):
        """Test CORS middleware is properly configured."""
        response = await async_client.options("/", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        })
        assert response.status_code == status.HTTP_200_OK
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers

    @pytest.mark.parametrize("endpoint", [
        "/auth/register",
        "/auth/login",
        "/resumes/create_resume"
    ])
    async def test_routes_exist(self, async_client: AsyncClient, endpoint: str):
        """Test that all expected routes are registered."""
        response = await async_client.options(endpoint)
        assert response.status_code != status.HTTP_404_NOT_FOUND

    async def test_validation_error_handler(self, async_client: AsyncClient):
        """Test custom validation error handler returns correct format."""
        # Try to register with invalid data to trigger validation error
        response = await async_client.post("/auth/register", json={
            "username": "",  # Invalid empty username
            "email": "not-an-email",  # Invalid email format
            "password": ""  # Invalid empty password
        })
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error_response = response.json()
        assert "error" in error_response
        assert error_response["error"] == "ValidationError"
        assert "message" in error_response
        assert "details" in error_response

    @pytest.mark.parametrize("exception_class,expected_status", [
        (UserAlreadyExistsError("test"), status.HTTP_409_CONFLICT),
        (AuthException("test", status.HTTP_401_UNAUTHORIZED), status.HTTP_401_UNAUTHORIZED),
        (HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="test"), status.HTTP_404_NOT_FOUND)
    ])
    async def test_exception_handlers(
            self,
            async_client: AsyncClient,
            exception_class: Exception,
            expected_status: int,
            monkeypatch
    ):
        """Test custom exception handlers return correct status codes and formats."""

        # Create a test endpoint that raises our test exception
        @app.get("/test-exception")
        async def test_exception():
            raise exception_class

        response = await async_client.get("/test-exception")
        assert response.status_code == expected_status
        error_response = response.json()
        assert "message" in error_response or "detail" in error_response

    async def test_health_check_headers(self, async_client: AsyncClient):
        """Test health check endpoint includes necessary headers."""
        response = await async_client.get("/")
        assert "content-type" in response.headers
        assert response.headers["content-type"] == "application/json"

    @pytest.mark.parametrize("method,endpoint", [
        ("GET", "/nonexistent"),
        ("POST", "/invalid"),
        ("PUT", "/unknown")
    ])
    async def test_404_handler(self, async_client: AsyncClient, method: str, endpoint: str):
        """Test 404 errors are handled correctly."""
        response = await async_client.request(method, endpoint)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        error_response = response.json()
        assert "detail" in error_response

    async def test_startup_event(self):
        """Test the application startup event handler."""
        # This depends on what you have in your startup event
        # For example, if you're initializing RabbitMQ:
        assert hasattr(app, "state")
        # Add more assertions based on what your startup event does

    async def test_shutdown_event(self):
        """Test the application shutdown event handler."""
        # This depends on what you have in your shutdown event
        # For example, if you're closing connections:
        # Add assertions based on what your shutdown event does
        pass


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()