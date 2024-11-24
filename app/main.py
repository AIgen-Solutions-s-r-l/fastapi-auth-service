from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.exceptions import AuthException
from app.core.rabbitmq_client import RabbitMQClient
from app.core.logging_config import LogConfig
from app.routers.auth_router import router as auth_router
from app.routers.resume_ingestor_router import router as resume_router

settings = Settings()

# Initialize logging
LogConfig.setup_logging(**settings.logging_config)
logger = LogConfig.get_logger()

def message_callback(ch, method, properties, body):
    """
    Callback function to process each message from RabbitMQ.

    Args:
        ch (Channel): The RabbitMQ channel.
        method: The RabbitMQ method frame.
        properties: The RabbitMQ properties.
        body (bytes): The message content.
    """
    logger.info(f"Received message: {body.decode()}")


# Global instance of RabbitMQClient
rabbit_client = RabbitMQClient(
    rabbitmq_url=settings.rabbitmq_url,
    queue="my_queue",
    callback=message_callback
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager to manage startup and shutdown events for FastAPI.
    Starts and stops the RabbitMQ client connection.
    """
    rabbit_thread = Thread(target=rabbit_client.start)
    rabbit_thread.start()
    logger.info("RabbitMQ client started in background thread")

    yield

    rabbit_client.stop()
    rabbit_thread.join()
    logger.info("RabbitMQ client connection closed")


app = FastAPI(
    title="Auth Service API",
    description="Authentication service",
    version="1.0.0",
    lifespan=lifespan
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
    logger.debug("Root endpoint accessed")
    return {"message": "authService is up and running!"}


# Include routers with appropriate prefixes
app.include_router(auth_router, prefix="/auth")
app.include_router(resume_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.error(f"Validation error: {exc.errors()}")
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
    logger.error(f"Auth exception: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )