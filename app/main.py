# app/main.py
import logging
from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.exceptions import AuthException
from app.core.rabbitmq_client import RabbitMQClient
from app.routers.auth_router import router as auth_router
from app.routers.resume_ingestor_router import router as resume_ingestor_router

logging.basicConfig(level=logging.DEBUG)

settings = Settings()


def message_callback(ch, method, properties, body):
    """
    Callback function to process each message from RabbitMQ.

    Args:
        ch (Channel): The RabbitMQ channel.
        method: The RabbitMQ method frame.
        properties: The RabbitMQ properties.
        body (bytes): The message content.
    """
    logging.info(f"Received message: {body.decode()}")


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
    logging.info("RabbitMQ client started in background thread")

    yield

    rabbit_client.stop()
    rabbit_thread.join()
    logging.info("RabbitMQ client connection closed")


# app = FastAPI(lifespan=lifespan)
app = FastAPI(
    title="Auth Service API",
    description="Authentication service",
    version="1.0.0"
)


# Root route for health check
@app.get("/")
async def root():
    """
    Root endpoint to test if the service is running.
    """
    return {"message": "authService is up and running!"}


# Include the authentication router
app.include_router(auth_router, prefix="/auth")
app.include_router(resume_ingestor_router, prefix="/resume_ingestor")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
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
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )
