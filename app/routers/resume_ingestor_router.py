# app/routers/resume_ingestor_router.py

import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query, Path
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.exceptions import ResumeNotFoundError
from app.models.user import User
from app.schemas.resume import Resume, ResumeResponse, ResumeRequest
from app.schemas.resume_utils import convert_json_to_resume_dict
from app.services.resume_service import (
    get_resume_by_user_id,
    add_resume,
    update_resume,
    delete_resume
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/resumes",
    tags=["resumes"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        500: {"description": "Internal server error"}
    }
)


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
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Create a new resume in the MongoDB database.

    Args:
        resume_data: Resume data to be stored
        db: Database session
        current_user: Currently authenticated user

    Returns:
        Dict containing the created resume data

    Raises:
        HTTPException: If validation fails or user not found
    """
    try:
        # Verify user exists and has permission
        if current_user.id != resume_data.user_id and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "NotAuthorized", "message": "Not authorized to create resume for this user"}
            )

        try:
            # Process and validate data
            processed_data = convert_json_to_resume_dict(resume_data.dict(), resume_data.user_id)
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
        user_id: int = Path(..., title="User ID", description="The ID of the user whose resume to retrieve", gt=0),
        version: Optional[str] = Query(None, description="Specific version of the resume to retrieve"),
        current_user: User = Depends(get_current_user)
) -> ResumeResponse:
    """
    Retrieve a user's resume from MongoDB.

    Args:
        user_id: ID of the user whose resume to retrieve
        version: Optional version of the resume to retrieve
        current_user: Currently authenticated user

    Returns:
        ResumeResponse containing the resume data

    Raises:
        HTTPException: If resume not found or user not authorized
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
        resume = await get_resume_by_user_id(user_id)
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


@router.put(
    "/{user_id}",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Resume successfully updated"},
        400: {"description": "Invalid resume data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized to update this resume"},
        404: {"description": "Resume not found"},
        500: {"description": "Internal server error"}
    }
)
async def update_user_resume(
        user_id: int,
        resume_data: ResumeRequest,
        current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Update an existing resume.

    Args:
        user_id: ID of the user whose resume to update
        resume_data: New resume data
        current_user: Currently authenticated user

    Returns:
        Dict containing the updated resume data

    Raises:
        HTTPException: If validation fails or user not authorized
    """
    # Authorization check
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "NotAuthorized",
                "message": "Not authorized to update this resume"
            }
        )

    try:
        # Process and validate data
        processed_data = convert_json_to_resume_dict(resume_data.dict(), user_id)
        resume = Resume.model_validate(processed_data)
        resume_dict = resume.model_dump(exclude_none=True)

        # Update in MongoDB
        result = await update_resume(user_id, resume_dict)
        if "error" in result:
            if "not found" in result["error"].lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"message": result["error"]}
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": result["error"]}
            )

        return result

    except ValidationError as e:
        logger.error(f"Data validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Invalid resume data", "errors": e.errors()}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating resume: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An error occurred while updating the resume"
            }
        )


@router.delete(
    "/{user_id}",
    response_model=Dict[str, str],
    responses={
        200: {"description": "Resume successfully deleted"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized to delete this resume"},
        404: {"description": "Resume not found"},
        500: {"description": "Internal server error"}
    }
)
async def delete_user_resume(
        user_id: int,
        current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Delete a user's resume.

    Args:
        user_id: ID of the user whose resume to delete
        current_user: Currently authenticated user

    Returns:
        Dict containing success message

    Raises:
        HTTPException: If resume not found or user not authorized
    """
    # Authorization check
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "NotAuthorized",
                "message": "Not authorized to delete this resume"
            }
        )

    try:
        result = await delete_resume(user_id)
        if result:
            return {"message": "Resume deleted successfully"}
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ResumeNotFound",
                "message": f"Resume not found for user_id: {user_id}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting resume: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An error occurred while deleting the resume"
            }
        )
