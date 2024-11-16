# app/services/resume_service.py
from typing import Dict, Any, Optional

from pymongo.errors import DuplicateKeyError

from app.core.mongodb import collection_name


async def get_resume_by_user_id(user_id: int, version: Optional[str] = None) -> Dict[str, Any]:
    """
    Function to retrieve a resume by user ID.

    Args:
        user_id: The user ID
        version: Optional version of the resume to retrieve

    Returns:
        Dict containing the resume data or error message if not found
    """
    try:
        query = {"user_id": user_id}
        if version:
            query["version"] = version

        resume = await collection_name.find_one(query)
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
        resume: The resume data as dictionary

    Returns:
        Dict containing the inserted resume data or error message
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
        user_id: The user ID whose resume needs to be updated
        resume_data: The new resume data

    Returns:
        Dict containing the updated resume data or error message
    """
    try:
        # Ensure we don't change the user_id
        resume_data["user_id"] = user_id

        # Check if resume exists
        existing_resume = await collection_name.find_one({"user_id": user_id})
        if not existing_resume:
            return {"error": f"Resume not found for user ID: {user_id}"}

        # Update the resume
        result = await collection_name.find_one_and_update(
            {"user_id": user_id},
            {"$set": resume_data},
            return_document=True
        )

        if not result:
            return {"error": f"Failed to update resume for user ID: {user_id}"}

        result["_id"] = str(result["_id"])
        return result

    except Exception as e:
        return {"error": f"Error updating resume: {str(e)}"}


async def delete_resume(user_id: int) -> bool:
    """
    Function to delete a resume.

    Args:
        user_id: The user ID whose resume needs to be deleted

    Returns:
        bool: True if resume was deleted, False if not found
    """
    try:
        # Check if resume exists
        existing_resume = await collection_name.find_one({"user_id": user_id})
        if not existing_resume:
            return False

        # Delete the resume
        result = await collection_name.delete_one({"user_id": user_id})
        return result.deleted_count > 0

    except Exception as e:
        raise Exception(f"Error deleting resume: {str(e)}")


async def list_resumes(skip: int = 0, limit: int = 10) -> Dict[str, Any]:
    """
    Function to list all resumes with pagination.

    Args:
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return

    Returns:
        Dict containing list of resumes and total count
    """
    try:
        # Get total count
        total_count = await collection_name.count_documents({})

        # Get paginated resumes
        cursor = collection_name.find({}).skip(skip).limit(limit)
        resumes = []
        async for resume in cursor:
            resume["_id"] = str(resume["_id"])
            resumes.append(resume)

        return {
            "total": total_count,
            "resumes": resumes,
            "skip": skip,
            "limit": limit
        }

    except Exception as e:
        return {"error": f"Error listing resumes: {str(e)}"}


async def search_resumes(
        query: Dict[str, Any],
        skip: int = 0,
        limit: int = 10
) -> Dict[str, Any]:
    """
    Function to search resumes based on criteria.

    Args:
        query: Search criteria
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return

    Returns:
        Dict containing list of matching resumes and total count
    """
    try:
        # Get total count of matching documents
        total_count = await collection_name.count_documents(query)

        # Get paginated matching resumes
        cursor = collection_name.find(query).skip(skip).limit(limit)
        resumes = []
        async for resume in cursor:
            resume["_id"] = str(resume["_id"])
            resumes.append(resume)

        return {
            "total": total_count,
            "resumes": resumes,
            "skip": skip,
            "limit": limit
        }

    except Exception as e:
        return {"error": f"Error searching resumes: {str(e)}"}
