# app/services/resume_service.py
import logging
from app.core.mongodb import collection_name

logger = logging.getLogger(__name__)


async def add_resume(resume_data: dict) -> dict:
    """Add a new resume to MongoDB."""
    try:
        existing_resume = await collection_name.find_one({"user_id": resume_data["user_id"]})

        if existing_resume:
            result = await collection_name.replace_one(
                {"user_id": resume_data["user_id"]},
                resume_data
            )
            if result.modified_count:
                return {"message": "Resume updated successfully"}
            return {"error": "Failed to update resume"}

        result = await collection_name.insert_one(resume_data)
        if result.inserted_id:
            return {"message": "Resume added successfully", "id": str(result.inserted_id)}
        return {"error": "Failed to add resume"}

    except Exception as e:
        logger.error(f"Error adding resume: {str(e)}")
        return {"error": f"Error adding resume: {str(e)}"}


async def get_resume_by_user_id(user_id: int) -> dict:
    """Retrieve a resume by user ID."""
    try:
        resume = await collection_name.find_one({"user_id": user_id})
        if resume:
            resume["_id"] = str(resume["_id"])
            return resume
        return {"error": "Resume not found"}
    except Exception as e:
        logger.error(f"Error retrieving resume: {str(e)}")
        return {"error": f"Error retrieving resume: {str(e)}"}