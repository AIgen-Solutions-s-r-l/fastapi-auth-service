# app/routers/resume_ingestor_router.py
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Body, Depends, status, Query, Path
from pydantic import ValidationError, BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.exceptions import (
    ResumeNotFoundError,
    ResumeDuplicateError,
    ResumeValidationError,
    DatabaseOperationError
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
    """Schema for resume response data."""
    message: str
    resume_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


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


@router.post(
    "/create",
    response_model=ResumeResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "Resume successfully created",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Resume created successfully",
                        "resume_id": "12345",
                        "data": {"personal_information": {...}}
                    }
                }
            }
        },
        400: {"description": "Invalid resume data"},
        404: {"description": "User not found"},
        409: {"description": "Resume already exists"},
        500: {"description": "Internal server error"}
    }
)
async def create_resume(
        json_data: Dict[str, Any] = Body(
            ...,
            example=ResumeExample.Config.json_schema_extra["example"]
        ),
        user_id: int = Path(..., description="The ID of the user who owns the resume"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> ResumeResponse:
    """
    Create or update a resume in the MongoDB database.

    This endpoint allows users to create or update their resume. The resume data
    should follow the specified schema and will be validated before storage.
    Only authenticated users can create resumes, and they can only create/update
    their own resumes.

    Args:
        json_data: The resume data in JSON format
        user_id: The ID of the user who owns the resume
        db: Database session dependency
        current_user: The currently authenticated user

    Returns:
        ResumeResponse: Contains confirmation message and resume data

    Raises:
        HTTPException:
            - 401: If user is not authenticated
            - 403: If user tries to modify another user's resume
            - 404: If user not found
            - 400: If resume data is invalid
            - 409: If resume already exists
            - 500: For internal server errors
    """
    # Authorization check
    if current_user.id != user_id:
        logger.warning(f"User {current_user.id} attempted to access resume of user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this resume"
        )

    try:
        # Verify user exists
        user = await db.get(User, user_id)
        if not user:
            logger.error(f"User not found: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "User not found", "user_id": user_id}
            )

        # Process and validate data
        try:
            processed_data = convert_json_to_resume_dict(json_data, user_id)
            resume = Resume.model_validate(processed_data)
            resume_dict = resume.model_dump(exclude_none=True)
        except ValidationError as e:
            logger.error(f"Resume validation error: {str(e)}")
            raise ResumeValidationError(str(e))

        # Store in MongoDB
        result = await add_resume(resume_dict)
        if "error" in result:
            raise DatabaseOperationError(result["error"])

        logger.info(f"Resume created successfully for user {user_id}")
        return ResumeResponse(
            message="Resume created successfully",
            resume_id=str(result.get("_id")),
            data=result
        )

    except (ResumeValidationError, ResumeDuplicateError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(e)}
        )
    except DatabaseOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": str(e)}
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "An unexpected error occurred"}
        )


@router.get(
    "/{user_id}",
    response_model=ResumeResponse,
    responses={
        200: {
            "description": "Resume successfully retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Resume retrieved successfully",
                        "data": {"personal_information": {...}}
                    }
                }
            }
        },
        404: {"description": "Resume not found"}
    }
)
async def get_resume(
        user_id: int = Path(..., description="The ID of the user whose resume to retrieve"),
        version: Optional[str] = Query(None, description="Specific version of the resume to retrieve"),
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
            detail="Not authorized to access this resume"
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(e)}
        )
    except Exception as e:
        logger.error(f"Error retrieving resume: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "An error occurred while retrieving the resume"}
        )

# ... Altri endpoint da aggiungere ...
