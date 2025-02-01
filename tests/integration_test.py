import httpx
import pytest

BASE_URL = "http://localhost:8001"

def test_root_endpoint():
    response = httpx.get(f"{BASE_URL}/")
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}"
    data = response.json()
    assert "message" in data, "Response JSON should have a 'message' key"
    assert data["message"] == "authService is up and running!", f"Unexpected message: {data['message']}"

def test_healthcheck_endpoint():
    response = httpx.get(f"{BASE_URL}/healthcheck")
    # Healthcheck might return 200 on success or 500 on failure
    assert response.status_code in (200, 500), f"Expected status code 200 or 500, got {response.status_code}"

def test_test_log_endpoint():
    response = httpx.get(f"{BASE_URL}/test-log")
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}"
    data = response.json()
    assert data.get("status") == "Log sent", f"Expected 'Log sent' but got {data.get('status')}"

def test_auth_router_base():
    # Depending on the auth_router implementation, this base route may not be defined.
    # We expect a 404 Not Found or 405 Method Not Allowed.
    response = httpx.get(f"{BASE_URL}/auth")
    assert response.status_code in (404, 405), f"Expected 404 or 405 but got {response.status_code}"

# Adding tests for additional default FastAPI routes and any other endpoints
@pytest.mark.parametrize("method,endpoint", [
    ("GET", "/"),             # Root endpoint
    ("GET", "/healthcheck"),  # Healthcheck
    ("GET", "/test-log"),     # Test log endpoint
    ("GET", "/auth"),         # Base auth route
    ("GET", "/docs"),         # Swagger docs
    ("GET", "/redoc"),        # ReDoc docs
    ("GET", "/openapi.json"), # OpenAPI schema
    # Add additional endpoints from the application as needed
])
def test_all_routes(method, endpoint):
    with httpx.Client() as client:
        if method.upper() == "GET":
            response = client.get(f"{BASE_URL}{endpoint}")
        else:
            response = client.request(method, f"{BASE_URL}{endpoint}")
    # Ensure that endpoints do not return server errors (status codes less than 500)
    assert response.status_code < 500, f"Endpoint {endpoint} returned error {response.status_code}"