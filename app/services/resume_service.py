# app/services/resume_service.py
from typing import Dict, Any, Optional
from pymongo.errors import DuplicateKeyError
from bson.objectid import ObjectId

from app.core.mongodb import collection_name


async def get_resume_by_user_id(user_id: int) -> Dict[str, Any]:
    """
    Function to retrieve a resume by user ID.

    Args:
        user_id (int): The user ID.

    Returns:
        Dict[str, Any]: The resume data or error message if not found.
    """
    try:
        resume = await collection_name.find_one({"user_id": user_id})
        if not resume:
            return {"error": f"Resume not found for user ID: {user_id}"}

        # Convert ObjectId to string for JSON serialization
        resume["_id"] = str(resume["_id"])
        return resume

    except Exception as e:
        return {"error": f"Error retrieving resume: {str(e)}"}


async def add_resume(resume: Dict[str, Any]) -> Dict[str, Any]:
    """
    Function to add a resume to the database.

    Args:
        resume (Dict[str, Any]): The resume data as dictionary.

    Returns:
        Dict[str, Any]: The inserted resume data or error message.
    """
    try:
        # Ensure user_id is an integer
        if isinstance(resume.get("user_id"), str):
            try:
                resume["user_id"] = int(resume["user_id"])
            except ValueError:
                return {"error": f"Invalid user ID format: {resume.get('user_id')}. Must be an integer."}

        # Check if resume already exists for this user
        existing_resume = await collection_name.find_one({"user_id": resume["user_id"]})
        if existing_resume:
            return {"error": f"Resume already exists for user ID: {resume['user_id']}"}

        # Insert the resume
        result = await collection_name.insert_one(resume)

        # Retrieve and return the inserted document
        inserted_resume = await collection_name.find_one({"_id": result.inserted_id})
        if inserted_resume:
            inserted_resume["_id"] = str(inserted_resume["_id"])
            return inserted_resume

        return {"error": "Failed to retrieve inserted resume"}

    except DuplicateKeyError:
        return {"error": f"Resume already exists for user ID: {resume.get('user_id')}"}
    except Exception as e:
        return {"error": f"Error adding resume: {str(e)}"}


async def update_resume(user_id: int, resume_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Function to update an existing resume.

    Args:
        user_id (int): The user ID whose resume needs to be updated.
        resume_data (Dict[str, Any]): The new resume data.

    Returns:
        Dict[str, Any]: The updated resume data or error message.
    """
    try:
        # Ensure we don't change the user_id
        resume_data["user_id"] = user_id

        result = await collection_name.find_one_and_update(
            {"user_id": user_id},
            {"$set": resume_data},
            return_document=True
        )

        if not result:
            return {"error": f"Resume not found for user ID: {user_id}"}

        result["_id"] = str(result["_id"])
        return result

    except Exception as e:
        return {"error": f"Error updating resume: {str(e)}"}