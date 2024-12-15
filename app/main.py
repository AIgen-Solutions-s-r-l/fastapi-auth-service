"""FastAPI application entry point for the Authentication Service."""

from contextlib import asynccontextmanager
from threading import Thread
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.exceptions import AuthException
from app.core.rabbitmq_client import RabbitMQClient
from app.core.logging_config import init_logging, test_connection
from app.routers.auth_router import router as auth_router

# Initialize settings
settings = Settings()

# Test connection first
test_connection(settings.syslog_host, settings.syslog_port)

# Initialize logger
logger = init_logging(settings)


def message_callback(ch, method, properties, body):
    """Callback function to process each message from RabbitMQ."""
    logger.info(
        "Received message from RabbitMQ",
        extra={
            "message_body": body.decode(),
            "exchange": method.exchange,
            "routing_key": method.routing_key,
            "event_type": "rabbitmq_message"
        }
    )


# Global instance of RabbitMQClient
rabbit_client = RabbitMQClient(
    rabbitmq_url=settings.rabbitmq_url,
    queue="my_queue",
    callback=message_callback
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # Startup
    rabbit_thread = Thread(target=rabbit_client.start)
    rabbit_thread.start()
    logger.info(
        "RabbitMQ client started",
        extra={
            "event_type": "service_startup",
            "component": "rabbitmq",
            "status": "started"
        }
    )

    yield

    # Shutdown
    rabbit_client.stop()
    rabbit_thread.join()
    logger.info(
        "RabbitMQ client stopped",
        extra={
            "event_type": "service_shutdown",
            "component": "rabbitmq",
            "status": "stopped"
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
