# tests/test_main.py

from typing import Generator

import pytest
from fastapi import HTTPException, status, APIRouter
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.core.exceptions import AuthException, UserAlreadyExistsError
from app.main import app


# Fixture per il client di test
@pytest.fixture
async def async_client() -> Generator:
    from httpx import AsyncClient
    async with AsyncClient(
            app=app,
            base_url="http://test",
            follow_redirects=True
    ) as client:
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
        origin = "http://localhost:3000"
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type"
        }
        response = await async_client.options(
            "/",
            headers=headers,
        )

        assert response.status_code == status.HTTP_200_OK, f"Response: {response.text}"
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-methods" in response.headers
        assert "GET" in response.headers["access-control-allow-methods"]

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

    test_router = None  # Variabile di classe per tenere traccia del router di test

    @pytest.mark.parametrize("exception_class,expected_status", [
        (UserAlreadyExistsError("test"), status.HTTP_409_CONFLICT),
        (AuthException("test", status.HTTP_401_UNAUTHORIZED), status.HTTP_401_UNAUTHORIZED),
        (HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="test"), status.HTTP_404_NOT_FOUND)
    ])
    async def test_exception_handlers(
            self,
            async_client: AsyncClient,
            exception_class: Exception,
            expected_status: int
    ):
        """Test custom exception handlers return correct status codes and formats."""

        # Rimuovi il router precedente se esiste
        if self.test_router:
            app.routes = [r for r in app.routes if r not in self.test_router.routes]

        # Crea un nuovo router con un path unico
        self.test_router = APIRouter()

        @self.test_router.get(f"/test-{expected_status}")
        async def test_route():
            raise exception_class

        app.include_router(self.test_router)

        response = await async_client.get(f"/test-{expected_status}")
        assert response.status_code == expected_status
        assert "detail" in response.json()

    @classmethod
    async def cleanup(cls):
        """Cleanup method to remove test routes"""
        if cls.test_router:
            app.routes = [r for r in app.routes if r not in cls.test_router.routes]
            cls.test_router = None

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
