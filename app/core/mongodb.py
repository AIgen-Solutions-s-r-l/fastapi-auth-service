# app/core/mongodb.py
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from app.core.config import Settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = Settings()

try:
    logger.info(f"MongoDB URL: {settings.mongodb_uri}")
    # Create MongoDB client with authentication
    client = AsyncIOMotorClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000  # Added timeout for better error handling
    )

    # Access the specific database
    database = client[settings.mongodb_database]

    # Get the collection
    collection_name = database.get_collection("resumes")

    # Verify connection
    client.admin.command('ping')
    logger.info(f"Successfully connected to MongoDB at {settings.mongodb_host}")

except Exception as e:
    logger.error(f"Error connecting to MongoDB: {str(e)}")
    raise