from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from app.core.config import Settings

MONGO_DETAILS = Settings.mongodb

client = AsyncIOMotorClient(MONGO_DETAILS)
database = client.your_database_name
collection_name = database.get_collection("resumes")


async def add_resume(resume: dict):
    """
    Function to add a resume to the database.
    Args:
        resume (dict): The resume data as dictionary.
    Returns:
        dict: The inserted resume data.
    """
    try:
        result = await collection_name.insert_one(resume)
    except DuplicateKeyError:
        return {"error": "Resume already exists"}

    inserted_resume = await collection_name.find_one({"_id": result.inserted_id})
    return inserted_resume


async def get_resume_by_user_id(user_id: str):
    """
    Function to retrieve a resume by user ID.
    Args:
        user_id (str): The user ID.
    Returns:
        dict: The resume data.
    """
    resume = await collection_name.find_one({"user_id": user_id})
    if not resume:
        return {"error": "Resume not found"}
    return resume
