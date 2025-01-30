"""FastAPI application entry point for the Authentication Service."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_sqlalchemy import DBSessionMiddleware

from app.core.config import Settings
from app.core.exceptions import AuthException
from app.core.logging_config import init_logging, test_connection
from app.routers.auth_router import router as auth_router
from app.routers.healthcheck_router import router as healthcheck_router

# Initialize settings
settings = Settings()

# Test logstash connection if enabled
if settings.enable_logstash:
    test_connection(settings.syslog_host, settings.syslog_port)

# Initialize logger
logger = init_logging(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # Startup
    logger.info(
        "Starting application",
        extra={
            "event_type": "service_startup",
            "component": "application",
            "status": "starting"
        }
    )

    yield

    # Shutdown
    logger.info(
        "Shutting down application",
        extra={
            "event_type": "service_shutdown",
            "component": "application",
            "status": "stopping"
        }
    )

# Initialize FastAPI app
app = FastAPI(
    title="Auth Service API",
    description="Authentication service",
    version="1.0.0",
    lifespan=lifespan
)

# Log application startup
logger.info(
    "Initializing application",
    extra={
        "event_type": "service_startup",
        "service_name": settings.service_name,
        "environment": settings.environment
    }
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

app.add_middleware(DBSessionMiddleware, db_url=settings.database_url)



@app.get("/")
async def root():
    """Root endpoint that returns service status"""
    logger.debug(
        "Root endpoint accessed",
        extra={
            "event_type": "endpoint_access",
            "endpoint": "root",
            "method": "GET"
        }
    )
    return {"message": "authService is up and running!"}

# Include routers
app.include_router(auth_router, prefix="/auth")
app.include_router(healthcheck_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """Handle validation exceptions and return formatted error response.

    Args:
        request: The incoming request
        exc: The validation exception

    Returns:
        JSONResponse with validation error details
    """
    logger.error(
        "Request validation error",
        extra={
            "event_type": "validation_error",
            "error_details": exc.errors(),
            "endpoint": request.url.path,
            "method": request.method
        }
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "message": "Invalid request data",
            "details": exc.errors()
        }
    )


@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException) -> JSONResponse:
    logger.error(
        "Authentication error",
        extra={
            "event_type": "auth_error",
            "error_details": exc.detail,
            "status_code": exc.status_code,
            "endpoint": request.url.path,
            "method": request.method
        }
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


@app.get("/test-log")
async def test_log():
    """Test endpoint for logging"""
    logger.info(
        "Test log message",
        extra={
            "test_id": "123",
            "custom_field": "test value",
            "event_type": "test_log"
        }
    )
    return {"status": "Log sent"}
