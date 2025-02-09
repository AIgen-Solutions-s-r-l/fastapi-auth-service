"""FastAPI application entry point for the Authentication Service."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_sqlalchemy import DBSessionMiddleware

from app.core.config import settings
from app.core.exceptions import AuthException
from app.core.error_handlers import validation_exception_handler, auth_exception_handler, http_exception_handler, generic_exception_handler
from app.log.logging import logger, InterceptHandler
from app.routers.auth_router import router as auth_router
from app.routers.healthcheck_router import router as healthcheck_router
from app.routers.credit_router import router as credit_router
import logging

#try to intercept standard messages toward your Loguru
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # Startup
    logger.info("Starting application",status="starting",event="service_startup")
    yield
    # Shutdown
    logger.info("Shutting down application",status="stopping",event="service_shutdown")


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
