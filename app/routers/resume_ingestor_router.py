# app/routers/resume_ingestor_router.py
import logging
from fastapi import APIRouter, HTTPException, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.services.resume_service import get_resume_by_user_id, add_resume
from app.schemas.resume import Resume
from app.schemas.resume_utils import convert_yaml_to_resume_dict

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/create_resume")
async def create_resume(
        yaml_data: dict = Body(...),
        user_id: int = Body(...),
        db: AsyncSession = Depends(get_db)
):
    """Create or update a resume in the MongoDB database."""
    try:
        # Verify user exists
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            # Convert and validate data
            processed_data = convert_yaml_to_resume_dict(yaml_data, user_id)
            resume = Resume.model_validate(processed_data)
            resume_dict = resume.model_dump(exclude_none=True)
        except Exception as e:
            logger.error(f"Data validation error: {str(e)}")
            raise ValueError(f"Invalid resume data: {str(e)}")

        # Store in MongoDB
        result = await add_resume(resume_dict)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing resume: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing the resume: {str(e)}"
        )


@router.get("/resume/{user_id}")
async def get_resume(user_id: int):
    """Retrieve a user's resume from MongoDB."""
    try:
        resume = await get_resume_by_user_id(user_id)
        if "error" in resume:
            raise HTTPException(status_code=404, detail=resume["error"])
        return resume
    except Exception as e:
        logger.error(f"Error retrieving resume: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while retrieving the resume: {str(e)}"
        )


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