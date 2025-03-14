"""FastAPI application entry point for the Authentication Service."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware 
from fastapi.responses import JSONResponse
from fastapi_sqlalchemy import DBSessionMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings, validate_email_config, validate_stripe_config, validate_internal_api_key
from app.core.exceptions import AuthException 
from app.core.error_handlers import (validation_exception_handler, auth_exception_handler, 
                                   http_exception_handler, generic_exception_handler,
                                   database_exception_handler, sqlalchemy_exception_handler)
from app.log.logging import logger, InterceptHandler
from app.core.db_exceptions import DatabaseException
from app.routers.auth_router import router as auth_router
from app.routers.healthcheck_router import router as healthcheck_router
from app.routers.credit_router import router as credit_router
from app.routers.stripe_webhook import router as stripe_webhook_router
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
    
    # Validate Stripe configuration
    stripe_config_valid, stripe_validation_details = validate_stripe_config()
    if not stripe_config_valid:
        logger.warning(
            "Stripe configuration is invalid or incomplete",
            event_type="startup_warning",
            component="stripe",
            issues=stripe_validation_details["issues"]
        )
    else:
        logger.info(
            "Stripe configuration validated successfully",
            event_type="startup_info",
            component="stripe",
            warnings=stripe_validation_details.get("warnings", [])
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
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

# Add DB session middleware
app.add_middleware(DBSessionMiddleware, db_url=settings.database_url)

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
app.include_router(stripe_webhook_router)

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
