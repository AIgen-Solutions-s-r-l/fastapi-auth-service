from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, List, Dict
from app.core.mongodb import add_resume, get_resume_by_user_id
from app.core.database import get_db
from app.models.user import User

router = APIRouter()

class Resume(BaseModel):
    """
    Pydantic model for representing a resume.

    Attributes:
        user_id (str): ID of the user submitting the resume.
        name (str): Name of the user.
        email (str): Email address of the user.
        experience (Any): Work experience details; should be replaced with a specific type or Pydantic model.
        education (Any): Education details; should be replaced with a specific type or Pydantic model.
        skills (List[str]): List of skills the user possesses.
    """
    user_id: str
    name: str
    email: str
    experience: Any  # Replace with a specific type or Pydantic model if the structure is known
    education: Any  # Replace with a specific type or Pydantic model if the structure is known
    skills: List[str]


@router.post("/create_resume", response_description="Add new resume")
async def ingest_resume(
    resume: Resume = Body(...),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Endpoint to ingest a new resume into the MongoDB database.

    This function first checks if the user exists in the PostgreSQL database. If the user exists,
    it then proceeds to store the resume in MongoDB. If an error occurs during the MongoDB insertion,
    an HTTP 400 error is raised.

    Args:
        resume (Resume): Resume data to be ingested, provided in the request body.
        db (AsyncSession): SQLAlchemy asynchronous session dependency for database interaction.

    Returns:
        Dict[str, Any]: Response from MongoDB upon successful addition of the resume.

    Raises:
        HTTPException: If the user is not found in PostgreSQL (404).
        HTTPException: If there's an error during resume insertion in MongoDB (400).
    """
    # Check if user exists in PostgreSQL
    user = await db.get(User, resume.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Convert resume data to dictionary format for MongoDB insertion
    resume_data = resume.model_dump()
    new_resume = await add_resume(resume_data)

    # Handle any potential errors from MongoDB
    if "error" in new_resume:
        raise HTTPException(status_code=400, detail=new_resume["error"])

    return new_resume


@router.get("/resume/{user_id}", response_description="Get resume by user ID")
async def get_resume(user_id: str) -> Dict[str, Any]:
    """
    Endpoint to retrieve a user's resume from MongoDB by their user ID.

    Args:
        user_id (str): The user ID to search for in MongoDB.

    Returns:
        Dict[str, Any]: Resume data associated with the provided user ID.

    Raises:
        HTTPException: If there's an error retrieving the resume from MongoDB or if no resume is found (404).
    """
    # Retrieve resume from MongoDB based on user ID
    resume = await get_resume_by_user_id(user_id)

    # Handle errors or missing data from MongoDB
    if "error" in resume:
        raise HTTPException(status_code=404, detail=resume["error"])

    return resume
