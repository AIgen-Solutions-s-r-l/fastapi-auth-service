# app/routers/resume_ingestor_router.py
from typing import Dict, Any
import logging
from fastapi import APIRouter, HTTPException, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.services.resume_service import get_resume_by_user_id, add_resume
from app.schemas.resume import Resume
from app.schemas.resume_utils import convert_yaml_to_resume_dict

# Configure logging
logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/create_resume", response_description="Add new resume")
async def create_resume(
        yaml_data: Dict[str, Any] = Body(...),
        user_id: int = Body(...),
        db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create or update a resume in the MongoDB database.
    """
    try:
        # Verify user exists
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Convert YAML to dictionary and validate with Pydantic model
        processed_data = convert_yaml_to_resume_dict(yaml_data, user_id)
        resume = Resume(**processed_data)

        # Convert to dict for MongoDB and store
        resume_dict = resume.model_dump(exclude_none=True)
        result = await add_resume(resume_dict)

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing resume: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing the resume: {str(e)}"
        )


@router.get("/resume/{user_id}", response_description="Get resume by user ID")
async def get_resume(user_id: int) -> Dict[str, Any]:
    """
    Retrieve a user's resume from MongoDB.
    """
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