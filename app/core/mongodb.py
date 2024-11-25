from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import Settings
from app.core.logging_config import LogConfig

logger = LogConfig.get_logger()
settings = Settings()

try:
    logger.info("Initializing MongoDB connection", extra={
        "event_type": "mongodb_init",
        "mongodb_host": settings.mongodb_host,
        "mongodb_database": settings.mongodb_database
    })

    client = AsyncIOMotorClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000
    )

    database = client[settings.mongodb_database]
    collection_name = database.get_collection("resumes")

    client.admin.command('ping')
    logger.info("MongoDB connection established", extra={
        "event_type": "mongodb_connected",
        "host": settings.mongodb_host,
        "database": settings.mongodb_database
    })

except Exception as e:
    logger.error("MongoDB connection failed", extra={
        "event_type": "mongodb_error",
        "error_type": type(e).__name__,
        "error_details": str(e)
    })
    raise