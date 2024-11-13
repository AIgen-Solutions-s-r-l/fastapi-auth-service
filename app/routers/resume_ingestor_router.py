# app/routers/resume_ingestor_router.py
import logging
from fastapi import APIRouter, HTTPException, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.services.resume_service import get_resume_by_user_id, add_resume
from app.schemas.resume import Resume

logger = logging.getLogger(__name__)
router = APIRouter()


def convert_yaml_to_resume_dict(yaml_data: dict, user_id: int) -> dict:
    """Simple YAML to dict conversion with boolean processing"""
    processed = yaml_data.copy()
    processed['user_id'] = user_id

    # Process booleans in legal_authorization
    auth = processed.get('legal_authorization', {})
    for key in auth:
        if isinstance(auth[key], str):
            auth[key] = auth[key].lower() == 'yes'

    # Process booleans in work_preferences
    prefs = processed.get('work_preferences', {})
    for key in prefs:
        if isinstance(prefs[key], str):
            prefs[key] = prefs[key].lower() == 'yes'

    # Process booleans in self_identification
    ident = processed.get('self_identification', {})
    for field in ['veteran', 'disability']:
        if field in ident and isinstance(ident[field], str):
            ident[field] = ident[field].lower() == 'yes'

    return processed


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
            # Process data
            processed_data = convert_yaml_to_resume_dict(yaml_data, user_id)

            # Validate using Pydantic
            resume = Resume.model_validate(processed_data)

            # Convert to dict for MongoDB
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