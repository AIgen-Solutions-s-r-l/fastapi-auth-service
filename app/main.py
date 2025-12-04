"""FastAPI application entry point for the Authentication Service."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware 
from fastapi.responses import JSONResponse
from fastapi_sqlalchemy import DBSessionMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings, validate_email_config, validate_internal_api_key, validate_oauth_config
from app.core.exceptions import AuthException
from app.core.error_handlers import (validation_exception_handler, auth_exception_handler,
                                   http_exception_handler, generic_exception_handler,
                                   database_exception_handler, sqlalchemy_exception_handler)
from app.log.logging import logger, InterceptHandler
from app.core.db_exceptions import DatabaseException
from app.middleware.rate_limit import setup_rate_limiting, limiter
from app.routers.auth import router as auth_router
from app.routers.healthcheck_router import router as healthcheck_router
from app.routers.credit_router import router as credit_router
from app.routers.webhooks.stripe_webhooks import router as stripe_webhooks_router # Corrected import
import logging

#try to intercept standard messages toward your Loguru
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # Startup
    logger.info("Starting application", status="starting", event="service_startup")
    
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
    
    yield
    # Shutdown
    logger.info("Shutting down application", status="stopping", event="service_shutdown")


# Initialize FastAPI app
app = FastAPI(
    title="Auth Service API",
    description="Authentication service",
    version="1.0.0",
    lifespan=lifespan
)

# Log application startup
logger.info(
    "Initializing application"
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.cors_methods_list,
    allow_headers=settings.cors_headers_list,
    max_age=settings.CORS_MAX_AGE,
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

# Include routers
app.include_router(auth_router, prefix="/auth")
app.include_router(healthcheck_router)
app.include_router(credit_router)
app.include_router(stripe_webhooks_router, prefix="/webhooks", tags=["Webhooks"]) # New router

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
