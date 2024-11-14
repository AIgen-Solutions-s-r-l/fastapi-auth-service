# app/routers/resume_ingestor_router.py
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.core.database import get_db
from app.models.user import User
from app.services.resume_service import get_resume_by_user_id, add_resume
from app.schemas.resume import Resume
from app.schemas.resume_utils import convert_json_to_resume_dict

logger = logging.getLogger(__name__)
router = APIRouter(tags=["resumes"], prefix="/resumes")


@router.post(
    "/create_resume",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Resume successfully created"},
        400: {"description": "Invalid resume data"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"}
    }
)
async def create_resume(
        json_data: Dict[str, Any] = Body(
            ...,
            example={
                "personal_information": {
                    "name": "Marco",
                    "surname": "Rossi",
                    "email": "marco.rossi@example.com"
                },
                "legal_authorization": {
                    "eu_work_authorization": "Yes",
                    "us_work_authorization": "No"
                }
            }
        ),
        user_id: int = Body(..., example=123),
        db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create or update a resume in the MongoDB database.

    Args:
        json_data: The resume data in JSON format
        user_id: The ID of the user who owns the resume
        db: Database session dependency

    Returns:
        Dict[str, Any]: The created/updated resume with MongoDB metadata

    Raises:
        HTTPException:
            - 404: If user not found
            - 400: If resume data is invalid
            - 500: For internal server errors
    """
    try:
        # Verify user exists
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "User not found", "user_id": user_id}
            )

        try:
            # Process and validate data
            processed_data = convert_json_to_resume_dict(json_data, user_id)
            resume = Resume.model_validate(processed_data)
            resume_dict = resume.model_dump(exclude_none=True)

        except ValidationError as e:
            logger.error(f"Data validation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Invalid resume data", "errors": e.errors()}
            )

        # Store in MongoDB
        result = await add_resume(resume_dict)
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": result["error"]}
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing resume: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "An error occurred while processing the resume",
                "error": str(e)
            }
        )


@router.get(
    "/resume/{user_id}",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Resume successfully retrieved"},
        404: {"description": "Resume not found"},
        500: {"description": "Internal server error"}
    }
)
async def get_resume(user_id: int) -> Dict[str, Any]:
    """
    Retrieve a user's resume from MongoDB.

    Args:
        user_id: The ID of the user whose resume to retrieve

    Returns:
        Dict[str, Any]: The user's resume data

    Raises:
        HTTPException:
            - 404: If resume not found
            - 500: For internal server errors
    """
    try:
        resume = await get_resume_by_user_id(user_id)
        if "error" in resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": resume["error"], "user_id": user_id}
            )
        return resume

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving resume: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "An error occurred while retrieving the resume",
                "error": str(e)
            }
        )