from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from app.core.mongodb import add_resume

# Initialize the router for handling resume-related endpoints
router = APIRouter()


# Define data models
class Experience(BaseModel):
    """Represents an individual's work experience."""
    job_title: str = Field(..., description="Title of the job position")
    company: str = Field(..., description="Name of the company")
    start_date: str = Field(..., description="Start date in YYYY-MM format")
    end_date: Optional[str] = Field(None, description="End date in YYYY-MM format or None if ongoing")
    description: Optional[str] = Field(None, description="Brief description of the role")


class Education(BaseModel):
    """Represents an individual's educational background."""
    institution: str = Field(..., description="Name of the educational institution")
    degree: str = Field(..., description="Degree obtained")
    field_of_study: Optional[str] = Field(None, description="Field of study (e.g., Computer Science)")
    graduation_year: Optional[int] = Field(None, description="Year of graduation")


class Resume(BaseModel):
    """Represents a resume with user details, experience, education, and skills."""
    user_id: str = Field(..., description="Unique identifier for the user")
    name: str = Field(..., description="Name of the user")
    email: EmailStr = Field(..., description="Email address of the user")
    experience: List[Experience] = Field(..., description="List of work experiences")
    education: List[Education] = Field(..., description="List of educational qualifications")
    skills: List[str] = Field(..., description="List of skills possessed by the user")


@router.post("/ingest_resume", response_description="Add new resume")
async def ingest_resume(resume: Resume = Body(...)) -> Dict[str, Any]:
    """
    Endpoint to add a new resume to the database.

    This endpoint ingests a user's resume, including personal information, work experience,
    educational background, and skills, and stores it in a MongoDB database.

    Args:
        resume (Resume): The resume data for the user to be added.

    Returns:
        Dict[str, Any]: Confirmation message with the stored resume data or an error message.

    Raises:
        HTTPException: If there's an error while saving the resume.
    """
    # Convert the resume data to a dictionary format
    resume_data = resume.model_dump()

    # Call the database function to save the resume data
    new_resume = await add_resume(resume_data)

    # Handle potential database errors
    if "error" in new_resume:
        raise HTTPException(status_code=400, detail=new_resume["error"])

    return new_resume
