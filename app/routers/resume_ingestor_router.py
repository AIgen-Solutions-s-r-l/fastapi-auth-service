# app/routers/resume_ingestor_router.py
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query, Path
from pydantic import ValidationError, BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.exceptions import (
    ResumeNotFoundError
)
from app.models.user import User
from app.schemas.resume import Resume
from app.schemas.resume_utils import convert_json_to_resume_dict
from app.services.resume_service import (
    get_resume_by_user_id,
    add_resume
)

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["resumes"],
    prefix="/resumes",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        500: {"description": "Internal server error"}
    }
)


class ResumeResponse(BaseModel):
    """Schema for resume response"""
    message: str
    data: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Resume retrieved successfully",
                "data": {
                    "personal_information": {
                        "name": "Marco",
                        "surname": "Rossi",
                        "email": "marco.rossi@example.com"
                    },
                    "education_details": [
                        {
                            "education_level": "Master's Degree",
                            "institution": "University Example",
                            "year_of_completion": "2020"
                        }
                    ]
                }
            }
        }


class PersonalInfo(BaseModel):
    """Schema for personal information in resume example."""
    name: str
    surname: str
    email: EmailStr
    phone: Optional[str] = None


class LegalInfo(BaseModel):
    """Schema for legal authorization information."""
    eu_work_authorization: str
    us_work_authorization: str


class ResumeExample(BaseModel):
    """Example schema for resume creation."""
    personal_information: PersonalInfo
    legal_authorization: LegalInfo

    class Config:
        json_schema_extra = {
            "example": {
                "personal_information": {
                    "name": "Marco",
                    "surname": "Rossi",
                    "email": "marco.rossi@example.com",
                    "phone": "+39 123 456 7890"
                },
                "legal_authorization": {
                    "eu_work_authorization": "Yes",
                    "us_work_authorization": "No"
                }
            }
        }


class ResumeRequest(BaseModel):
    """Schema for resume creation request."""
    personal_information: Dict[str, Any]
    user_id: int

    class Config:
        json_schema_extra = {
            "example": {
                "personal_information": {
                    "name": "Marco",
                    "surname": "Rossi",
                    "email": "marco.rossi@example.com"
                },
                "user_id": 123
            }
        }


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
        resume_data: ResumeRequest,
        db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create or update a resume in the MongoDB database.
    """
    try:
        # Verify user exists
        user = await db.get(User, resume_data.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "User not found", "user_id": resume_data.user_id}
            )

        try:
            # Process and validate data
            processed_data = convert_json_to_resume_dict(resume_data.personal_information, resume_data.user_id)
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
    "/{user_id}",
    response_model=ResumeResponse,
    responses={
        200: {
            "description": "Resume successfully retrieved",
            "model": ResumeResponse
        },
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized to access this resume"},
        404: {"description": "Resume not found"},
        500: {"description": "Internal server error"}
    }
)
async def get_resume(
        user_id: int = Path(
            ...,  # ... è ok qui perché è un parametro Path
            title="User ID",
            description="The ID of the user whose resume to retrieve",
            gt=0
        ),
        version: Optional[str] = Query(
            None,
            title="Resume Version",
            description="Specific version of the resume to retrieve",
            example="1.0"
        ),
        current_user: User = Depends(get_current_user)
) -> ResumeResponse:
    """
    Retrieve a user's resume from MongoDB.

    This endpoint retrieves a user's resume. Users can only access their own resumes
    unless they have administrative privileges. Optional version parameter allows
    retrieving specific versions of the resume if versioning is implemented.

    Args:
        user_id: The ID of the user whose resume to retrieve
        version: Optional version of the resume to retrieve
        current_user: The currently authenticated user

    Returns:
        ResumeResponse: The user's resume data

    Raises:
        HTTPException:
            - 401: If user is not authenticated
            - 403: If user tries to access another user's resume
            - 404: If resume not found
            - 500: For internal server errors
    """
    # Authorization check
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "NotAuthorized",
                "message": "Not authorized to access this resume"
            }
        )

    try:
        resume = await get_resume_by_user_id(user_id, version)
        if "error" in resume:
            raise ResumeNotFoundError(f"user_id: {user_id}")

        logger.info(f"Resume retrieved successfully for user {user_id}")
        return ResumeResponse(
            message="Resume retrieved successfully",
            data=resume
        )

    except ResumeNotFoundError as e:
        logger.warning(f"Resume not found: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ResumeNotFound",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Error retrieving resume: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An error occurred while retrieving the resume"
            }
        )
