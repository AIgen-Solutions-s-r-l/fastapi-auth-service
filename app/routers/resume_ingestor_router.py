import os
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status, Query, Path
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.exceptions import ResumeNotFoundError
from app.core.logging_config import LogConfig
from app.models.user import User
from app.schemas.resume import Resume, ResumeResponse, ResumeRequest
from app.schemas.resume_utils import convert_json_to_resume_dict
from app.services.resume_service import (
    get_resume_by_user_id,
    add_resume,
    update_resume,
    delete_resume
)

logger = LogConfig.get_logger()

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
    """Create a new resume in the MongoDB database."""
    try:
        if current_user.id != resume_data.user_id and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "NotAuthorized", "message": "Not authorized to create resume for this user"}
            )

        try:
            processed_data = convert_json_to_resume_dict(resume_data.model_dump(), resume_data.user_id)
            resume = Resume.model_validate(processed_data)
            resume_dict = resume.model_dump(exclude_none=True)

        except ValidationError as e:
            logger.error("Resume data validation error", extra={
                "event_type": "resume_validation_error",
                "user_id": current_user.id,
                "error_details": str(e),
                "errors": e.errors()
            })
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Invalid resume data", "errors": e.errors()}
            )

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
        logger.error("Resume processing error", extra={
            "event_type": "resume_creation_error",
            "user_id": current_user.id,
            "error_details": str(e)
        })
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
    """Retrieve a user's resume from MongoDB."""
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

        logger.info("Resume retrieved", extra={
            "event_type": "resume_retrieved",
            "user_id": user_id,
            "version": version
        })
        return ResumeResponse(
            message="Resume retrieved successfully",
            data=resume
        )

    except ResumeNotFoundError as e:
        logger.warning("Resume not found", extra={
            "event_type": "resume_not_found",
            "user_id": user_id,
            "error_details": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ResumeNotFound",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error("Resume retrieval error", extra={
            "event_type": "resume_retrieval_error",
            "user_id": user_id,
            "error_details": str(e)
        })
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
    """Update an existing resume."""
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "NotAuthorized",
                "message": "Not authorized to update this resume"
            }
        )

    try:
        processed_data = convert_json_to_resume_dict(resume_data.model_dump(), resume_data.user_id)
        resume = Resume.model_validate(processed_data)
        resume_dict = resume.model_dump(exclude_none=True)

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
        logger.error("Resume validation error", extra={
            "event_type": "resume_update_validation_error",
            "user_id": user_id,
            "error_details": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Invalid resume data", "errors": e.errors()}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Resume update error", extra={
            "event_type": "resume_update_error",
            "user_id": user_id,
            "error_details": str(e)
        })
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
    """Delete a user's resume."""
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
        logger.error("Resume deletion error", extra={
            "event_type": "resume_deletion_error",
            "user_id": user_id,
            "error_details": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "InternalServerError",
                "message": "An error occurred while deleting the resume"
            }
        )