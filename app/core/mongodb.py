from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import Settings

settings = Settings()
MONGO_DETAILS = settings.mongodb

client = AsyncIOMotorClient(MONGO_DETAILS)
database = client.resumes
collection_name = database.get_collection("resumes")


