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

        # Debug: print input data
        logger.info(f"Received YAML data: {yaml_data}")
        logger.info(f"User ID: {user_id}")

        try:
            # Convert data
            processed_data = convert_yaml_to_resume_dict(yaml_data, user_id)
            logger.info(f"Processed data: {processed_data}")

            # Try constructing the resume manually first
            logger.info("Creating Resume object...")

            # Create Resume object field by field
            personal_info = processed_data.get('personal_information', {})
            education = processed_data.get('education_details', [])
            experience = processed_data.get('experience_details', [])
            projects = processed_data.get('projects', [])
            achievements = processed_data.get('achievements', [])
            certifications = processed_data.get('certifications', [])
            languages = processed_data.get('languages', [])
            interests = processed_data.get('interests', [])
            availability = processed_data.get('availability', {})
            salary = processed_data.get('salary_expectations', {})
            self_id = processed_data.get('self_identification', {})
            legal_auth = processed_data.get('legal_authorization', {})
            work_prefs = processed_data.get('work_preferences', {})

            # Debug: print each section before validation
            logger.info("Validating Personal Information...")
            resume = Resume(
                user_id=user_id,
                personal_information=personal_info,
                education_details=education,
                experience_details=experience,
                projects=projects,
                achievements=achievements,
                certifications=certifications,
                languages=languages,
                interests=interests,
                availability=availability,
                salary_expectations=salary,
                self_identification=self_id,
                legal_authorization=legal_auth,
                work_preferences=work_prefs
            )

            logger.info("Resume object created successfully")
            resume_dict = resume.model_dump(exclude_none=True)
            logger.info("Resume converted to dict successfully")

        except Exception as e:
            logger.error(f"Data validation error: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            logger.error(f"Error args: {e.args}")
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
