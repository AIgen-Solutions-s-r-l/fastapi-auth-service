from typing import Dict, Any, Optional
from pymongo.errors import DuplicateKeyError
from app.core.mongodb import collection_name
from app.core.logging_config import LogConfig

logger = LogConfig.get_logger()


async def get_resume_by_user_id(user_id: int, version: Optional[str] = None) -> Dict[str, Any]:
    try:
        query = {"user_id": user_id}
        if version:
            query["version"] = version

        resume = await collection_name.find_one(query)
        if not resume:
            logger.warning("Resume not found", extra={
                "event_type": "resume_not_found",
                "user_id": user_id,
                "version": version
            })
            return {"error": f"Resume not found for user ID: {user_id}"}

        resume["_id"] = str(resume["_id"])
        logger.info("Resume retrieved", extra={
            "event_type": "resume_retrieved",
            "user_id": user_id,
            "version": version
        })
        return resume

    except Exception as e:
        logger.error("Resume retrieval error", extra={
            "event_type": "resume_retrieval_error",
            "user_id": user_id,
            "error_type": type(e).__name__,
            "error_details": str(e)
        })
        return {"error": f"Error retrieving resume: {str(e)}"}


async def add_resume(resume: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if isinstance(resume.get("user_id"), str):
            try:
                resume["user_id"] = int(resume["user_id"])
            except ValueError:
                logger.error("Invalid user ID format", extra={
                    "event_type": "resume_validation_error",
                    "user_id": resume.get("user_id")
                })
                return {"error": f"Invalid user ID format: {resume.get('user_id')}. Must be an integer."}

        existing_resume = await collection_name.find_one({"user_id": resume["user_id"]})
        if existing_resume:
            logger.warning("Resume already exists", extra={
                "event_type": "resume_duplicate",
                "user_id": resume["user_id"]
            })
            return {"error": f"Resume already exists for user ID: {resume['user_id']}"}

        result = await collection_name.insert_one(resume)
        inserted_resume = await collection_name.find_one({"_id": result.inserted_id})

        if inserted_resume:
            inserted_resume["_id"] = str(inserted_resume["_id"])
            logger.info("Resume created", extra={
                "event_type": "resume_created",
                "user_id": resume["user_id"]
            })
            return inserted_resume

        logger.error("Resume insertion failed", extra={
            "event_type": "resume_creation_error",
            "user_id": resume["user_id"]
        })
        return {"error": "Failed to retrieve inserted resume"}

    except DuplicateKeyError:
        logger.error("Duplicate resume", extra={
            "event_type": "resume_duplicate_error",
            "user_id": resume.get("user_id")
        })
        return {"error": f"Resume already exists for user ID: {resume.get('user_id')}"}
    except Exception as e:
        logger.error("Resume creation error", extra={
            "event_type": "resume_creation_error",
            "user_id": resume.get("user_id"),
            "error_type": type(e).__name__,
            "error_details": str(e)
        })
        return {"error": f"Error adding resume: {str(e)}"}


async def update_resume(user_id: int, resume_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        resume_data["user_id"] = user_id
        existing_resume = await collection_name.find_one({"user_id": user_id})

        if not existing_resume:
            logger.warning("Resume not found for update", extra={
                "event_type": "resume_not_found",
                "user_id": user_id
            })
            return {"error": f"Resume not found for user ID: {user_id}"}

        result = await collection_name.find_one_and_update(
            {"user_id": user_id},
            {"$set": resume_data},
            return_document=True
        )

        if not result:
            logger.error("Resume update failed", extra={
                "event_type": "resume_update_error",
                "user_id": user_id
            })
            return {"error": f"Failed to update resume for user ID: {user_id}"}

        result["_id"] = str(result["_id"])
        logger.info("Resume updated", extra={
            "event_type": "resume_updated",
            "user_id": user_id
        })
        return result

    except Exception as e:
        logger.error("Resume update error", extra={
            "event_type": "resume_update_error",
            "user_id": user_id,
            "error_type": type(e).__name__,
            "error_details": str(e)
        })
        return {"error": f"Error updating resume: {str(e)}"}


async def delete_resume(user_id: int) -> bool:
    try:
        existing_resume = await collection_name.find_one({"user_id": user_id})
        if not existing_resume:
            logger.warning("Resume not found for deletion", extra={
                "event_type": "resume_not_found",
                "user_id": user_id
            })
            return False

        result = await collection_name.delete_one({"user_id": user_id})
        success = result.deleted_count > 0

        if success:
            logger.info("Resume deleted", extra={
                "event_type": "resume_deleted",
                "user_id": user_id
            })
        return success

    except Exception as e:
        logger.error("Resume deletion error", extra={
            "event_type": "resume_deletion_error",
            "user_id": user_id,
            "error_type": type(e).__name__,
            "error_details": str(e)
        })
        return False


async def list_resumes(skip: int = 0, limit: int = 10) -> Dict[str, Any]:
    try:
        total_count = await collection_name.count_documents({})
        cursor = collection_name.find({}).skip(skip).limit(limit)
        resumes = []

        async for resume in cursor:
            resume["_id"] = str(resume["_id"])
            resumes.append(resume)

        logger.info("Resumes listed", extra={
            "event_type": "resumes_listed",
            "total_count": total_count,
            "skip": skip,
            "limit": limit
        })
        return {
            "total": total_count,
            "resumes": resumes,
            "skip": skip,
            "limit": limit
        }

    except Exception as e:
        logger.error("Resume listing error", extra={
            "event_type": "resume_list_error",
            "error_type": type(e).__name__,
            "error_details": str(e),
            "skip": skip,
            "limit": limit
        })
        return {"error": f"Error listing resumes: {str(e)}"}


async def search_resumes(
        query: Dict[str, Any],
        skip: int = 0,
        limit: int = 10
) -> Dict[str, Any]:
    try:
        total_count = await collection_name.count_documents(query)
        cursor = collection_name.find(query).skip(skip).limit(limit)
        resumes = []

        async for resume in cursor:
            resume["_id"] = str(resume["_id"])
            resumes.append(resume)

        logger.info("Resumes searched", extra={
            "event_type": "resumes_searched",
            "query": query,
            "total_count": total_count,
            "skip": skip,
            "limit": limit
        })
        return {
            "total": total_count,
            "resumes": resumes,
            "skip": skip,
            "limit": limit
        }

    except Exception as e:
        logger.error("Resume search error", extra={
            "event_type": "resume_search_error",
            "error_type": type(e).__name__,
            "error_details": str(e),
            "query": query,
            "skip": skip,
            "limit": limit
        })
        return {"error": f"Error searching resumes: {str(e)}"}