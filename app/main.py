"""FastAPI application entry point for the Authentication Service."""

import signal
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_sqlalchemy import DBSessionMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings, validate_email_config, validate_internal_api_key, validate_oauth_config
from app.core.secrets_validator import validate_secrets_on_startup
from app.core.exceptions import AuthException
from app.core.error_handlers import (validation_exception_handler, auth_exception_handler,
                                   http_exception_handler, generic_exception_handler,
                                   database_exception_handler, sqlalchemy_exception_handler)
from app.log.logging import logger, InterceptHandler
from app.core.db_exceptions import DatabaseException
from app.middleware.rate_limit import setup_rate_limiting, limiter
from app.middleware.request_id import setup_request_id_middleware
from app.middleware.security_headers import setup_security_headers
from app.middleware.timeout import setup_timeout_middleware
from app.core.versioning import APIVersion, include_versioned_router
from app.routers.auth import router as auth_router
from app.routers.healthcheck_router import router as healthcheck_router, set_shutdown_state
from app.routers.credit_router import router as credit_router
from app.routers.webhooks.stripe_webhooks import router as stripe_webhooks_router # Corrected import
import logging

#try to intercept standard messages toward your Loguru
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

# Graceful shutdown state
_shutdown_event = asyncio.Event()
_active_requests = 0


def get_shutdown_event() -> asyncio.Event:
    """Get the shutdown event for coordination."""
    return _shutdown_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application with graceful shutdown."""
    # Startup
    logger.info("Starting application", status="starting", event="service_startup")

    # Validate secrets and sensitive configuration
    secrets_valid, secrets_details = validate_secrets_on_startup(settings)
    if not secrets_valid:
        logger.critical(
            "Application starting with critical secrets validation failures",
            event_type="startup_secrets_critical",
            issues=secrets_details.get("issues", [])
        )
        # In production, you might want to prevent startup here
        # raise RuntimeError("Critical secrets validation failures - cannot start safely")

    # Validate email configuration
    email_config_valid, validation_details = validate_email_config()
    if not email_config_valid:
        logger.warning(
            "Email configuration is invalid or incomplete",
            event_type="startup_warning",
            component="email",
            issues=validation_details["issues"]
        )
    else:
        logger.info(
            "Email configuration validated successfully",
            event_type="startup_info",
            component="email",
            warnings=validation_details.get("warnings", [])
        )


    # Validate internal API key configuration
    internal_api_key_valid, api_key_validation_details = validate_internal_api_key()
    if not internal_api_key_valid:
        logger.warning(
            "Internal API key configuration is invalid or incomplete",
            event_type="startup_warning",
            component="internal_service_auth",
            issues=api_key_validation_details["issues"]
        )
    else:
        logger.info(
            "Internal API key configuration validated successfully",
            event_type="startup_info",
            component="internal_service_auth",
            warnings=api_key_validation_details.get("warnings", [])
        )

    # Validate OAuth configuration
    oauth_config_valid, oauth_validation_details = validate_oauth_config()
    if not oauth_config_valid:
        logger.warning(
            "OAuth configuration is invalid or incomplete",
            event_type="startup_warning",
            component="oauth",
            issues=oauth_validation_details["issues"]
        )
    else:
        logger.info(
            "OAuth configuration validated successfully",
            event_type="startup_info",
            component="oauth",
            warnings=oauth_validation_details.get("warnings", [])
        )

    logger.info("Application startup complete", status="running", event="service_ready")

    yield

    # Graceful shutdown
    logger.info("Initiating graceful shutdown", status="stopping", event="service_shutdown_start")

    # Signal shutdown to health checks (readiness probe will start failing)
    _shutdown_event.set()
    set_shutdown_state(True)

    # Give time for load balancer to stop sending traffic (Kubernetes grace period)
    shutdown_grace_seconds = 5
    logger.info(
        f"Waiting {shutdown_grace_seconds}s for load balancer to drain traffic",
        event="shutdown_drain",
        grace_seconds=shutdown_grace_seconds
    )
    await asyncio.sleep(shutdown_grace_seconds)

    # Wait for active requests to complete (with timeout)
    max_wait_seconds = 30
    waited = 0
    while _active_requests > 0 and waited < max_wait_seconds:
        logger.info(
            f"Waiting for {_active_requests} active requests to complete",
            event="shutdown_waiting",
            active_requests=_active_requests
        )
        await asyncio.sleep(1)
        waited += 1

    if _active_requests > 0:
        logger.warning(
            f"Forcing shutdown with {_active_requests} requests still active",
            event="shutdown_forced",
            active_requests=_active_requests
        )

    logger.info("Application shutdown complete", status="stopped", event="service_shutdown_complete")


# OpenAPI tags metadata for API documentation
tags_metadata = [
    {
        "name": "Authentication",
        "description": "User authentication operations including login, registration, and token management."
    },
    {
        "name": "OAuth",
        "description": "OAuth 2.0 social authentication with Google."
    },
    {
        "name": "Password",
        "description": "Password management including change and reset operations."
    },
    {
        "name": "Email",
        "description": "Email verification and change operations."
    },
    {
        "name": "User Profile",
        "description": "User profile and status information."
    },
    {
        "name": "Credits",
        "description": "Credit balance and transaction operations."
    },
    {
        "name": "Subscriptions",
        "description": "Subscription management operations."
    },
    {
        "name": "Webhooks",
        "description": "Webhook endpoints for external service integrations."
    },
    {
        "name": "Health",
        "description": "Service health check endpoints."
    },
    {
        "name": "Internal",
        "description": "Internal service-to-service endpoints (requires API key)."
    }
]

# Initialize FastAPI app with comprehensive OpenAPI documentation
app = FastAPI(
    title="Auth Service API",
    description="""
## Authentication Microservice

A comprehensive authentication service providing:

* **User Authentication** - Email/password login and registration
* **OAuth 2.0** - Social authentication with Google
* **JWT Tokens** - Secure access token management
* **Email Verification** - Account verification via email
* **Password Management** - Secure password change and reset
* **Credit System** - User credit balance and transactions
* **Stripe Integration** - Payment processing and subscriptions

### Authentication

Most endpoints require authentication via JWT Bearer token:
```
Authorization: Bearer <access_token>
```

Internal service endpoints require API key authentication:
```
X-API-Key: <internal_api_key>
```

### Rate Limiting

Authentication endpoints are rate-limited to prevent brute force attacks.
Rate limit headers are included in responses:
- `X-RateLimit-Limit`: Maximum requests per window
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Time when the rate limit resets

### Request Tracking

All requests include a unique request ID for tracing:
- Sent in `X-Request-ID` response header
- Included in error responses for debugging
""",
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "syntaxHighlight.theme": "monokai"
    }
)

# Log application startup
logger.info(
    "Initializing application"
)

# Setup request ID middleware (must be early in the chain to track all requests)
setup_request_id_middleware(app)

# Setup security headers middleware
setup_security_headers(app)
logger.info("Security headers middleware configured", event="middleware_setup", middleware="security_headers")

# Setup request timeout middleware (30 seconds default)
setup_timeout_middleware(app, timeout_seconds=30.0)
logger.info("Timeout middleware configured", event="middleware_setup", middleware="timeout", timeout_seconds=30.0)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.cors_methods_list,
    allow_headers=settings.cors_headers_list,
    max_age=settings.CORS_MAX_AGE,
    expose_headers=["X-Request-ID"],  # Expose request ID header to clients
)

# Log CORS configuration at startup
logger.info(
    "CORS configured",
    origins=settings.cors_origins_list,
    methods=settings.cors_methods_list,
    credentials=settings.CORS_ALLOW_CREDENTIALS
)

# Add DB session middleware
app.add_middleware(DBSessionMiddleware, db_url=settings.database_url)

# Setup rate limiting
setup_rate_limiting(app)

# Register exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(AuthException, auth_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(DatabaseException, database_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

@app.get("/")
async def root():
    """Root endpoint that returns service status"""
    logger.debug("Root endpoint accessed",event="endpoint_access",endpoint="root",method="GET")
    return {"message": "authService is up and running!"}


@app.get("/api/versions", tags=["API Info"])
async def get_api_versions():
    """
    Get information about supported API versions.

    Returns a list of all supported API versions with their status.
    Use this endpoint to discover which API versions are available.
    """
    return {
        "current_version": APIVersion.latest().value,
        "supported_versions": [
            {
                "version": version.value,
                "status": "stable" if version == APIVersion.latest() else "supported",
                "base_path": f"/{version.value}"
            }
            for version in APIVersion.supported()
        ],
        "deprecation_notice": "Non-versioned endpoints (e.g., /auth/*) are deprecated. Please migrate to versioned endpoints (e.g., /v1/auth/*)"
    }

# Include routers with API versioning
# Versioned API routes (v1)
include_versioned_router(app, auth_router, "auth", [APIVersion.V1])
include_versioned_router(app, credit_router, "credits", [APIVersion.V1])
include_versioned_router(app, stripe_webhooks_router, "webhooks", [APIVersion.V1], tags=["Webhooks"])

# Legacy routes (for backward compatibility - will be deprecated)
app.include_router(auth_router, prefix="/auth")
app.include_router(credit_router)
app.include_router(stripe_webhooks_router, prefix="/webhooks", tags=["Webhooks"])

# Non-versioned routes (health checks should be version-agnostic)
app.include_router(healthcheck_router)

logger.info(
    "API routes registered",
    event="routes_registered",
    api_version=APIVersion.latest().value,
    supported_versions=[v.value for v in APIVersion.supported()]
)

# @app.get("/test-log")
# async def test_log():
#     """Test endpoint for logging"""
#     logger.info(
#         "Test log message",
#         extra={
#             "test_id": "123",
#             "custom_field": "test value",
#             "event_type": "test_log"
#         }
#     )
#     return {"status": "Log sent"}
