import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import Settings
from app.core.rabbitmq_client import RabbitMQClient
from app.routers.resume_ingestor_router import router as resume_ingestor_router
from app.routers.auth_router import router as auth_router
from threading import Thread

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

app = FastAPI(lifespan=lifespan)

# Root route for health check
@app.get("/")
async def root():
    """
    Root endpoint to test if the service is running.
    """
    return {"message": "authService is up and running!"}

# Include the authentication router
app.include_router(auth_router, prefix="/auth")
app.include_router(resume_ingestor_router, tags=["resume_ingestor"], prefix="/resume_ingestor")
