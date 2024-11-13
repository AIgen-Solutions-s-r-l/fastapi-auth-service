from fastapi import APIRouter, HTTPException, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.services.resume_service import get_resume_by_user_id, add_resume

router = APIRouter()

from typing import List, Dict, Any
from pydantic import BaseModel, EmailStr, HttpUrl, Field


class Language(BaseModel):
    language: str
    proficiency: str


class Project(BaseModel):
    name: str
    description: str
    link: HttpUrl


class Achievement(BaseModel):
    name: str
    description: str


class Certification(BaseModel):
    name: str
    description: str


class Education(BaseModel):
    education_level: str
    institution: str
    field_of_study: str
    final_evaluation_grade: str
    start_date: str
    year_of_completion: str
    exam: Dict[str, str]


class Experience(BaseModel):
    position: str
    company: str
    employment_period: str
    location: str
    industry: str
    key_responsibilities: List[Dict[str, str]]
    skills_acquired: List[str]


class WorkAuthorization(BaseModel):
    eu_work_authorization: bool
    us_work_authorization: bool
    requires_us_visa: bool
    requires_us_sponsorship: bool
    requires_eu_visa: bool
    legally_allowed_to_work_in_eu: bool
    legally_allowed_to_work_in_us: bool
    requires_eu_sponsorship: bool
    canada_work_authorization: bool
    requires_canada_visa: bool
    legally_allowed_to_work_in_canada: bool
    requires_canada_sponsorship: bool
    uk_work_authorization: bool
    requires_uk_visa: bool
    legally_allowed_to_work_in_uk: bool
    requires_uk_sponsorship: bool


class WorkPreferences(BaseModel):
    remote_work: bool
    in_person_work: bool
    open_to_relocation: bool
    willing_to_complete_assessments: bool
    willing_to_undergo_drug_tests: bool
    willing_to_undergo_background_checks: bool


class PersonalInformation(BaseModel):
    name: str
    surname: str
    date_of_birth: str
    country: str
    city: str
    address: str
    phone_prefix: str
    phone: str
    email: EmailStr
    github: HttpUrl
    linkedin: HttpUrl


class SelfIdentification(BaseModel):
    gender: str
    pronouns: str
    veteran: bool
    disability: bool
    ethnicity: str


class Resume(BaseModel):
    user_id: str = Field(..., description="ID of the user submitting the resume")
    personal_information: PersonalInformation
    education_details: List[Education]
    experience_details: List[Experience]
    projects: List[Project]
    achievements: List[Achievement]
    certifications: List[Certification]
    languages: List[Language]
    interests: List[str]
    availability: Dict[str, str]
    salary_expectations: Dict[str, str]
    self_identification: SelfIdentification
    legal_authorization: WorkAuthorization
    work_preferences: WorkPreferences


def convert_yaml_to_resume_json(yaml_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    Convert YAML data to a structured JSON format using Pydantic models.

    Args:
        yaml_data: The parsed YAML data
        user_id: The user ID to include in the resume

    Returns:
        Dict containing the structured resume data
    """

    # Convert string "Yes"/"No" to boolean
    def str_to_bool(s: str) -> bool:
        return s.lower() == "yes"

    # Convert work authorization fields
    work_auth = yaml_data['legal_authorization']
    for key in work_auth:
        work_auth[key] = str_to_bool(work_auth[key])

    # Convert work preferences
    work_prefs = yaml_data['work_preferences']
    for key in work_prefs:
        work_prefs[key] = str_to_bool(work_prefs[key])

    # Convert self identification fields
    self_id = yaml_data['self_identification']
    self_id['veteran'] = str_to_bool(self_id['veteran'])
    self_id['disability'] = str_to_bool(self_id['disability'])

    # Create the resume object
    resume_data = Resume(
        user_id=user_id,
        personal_information=PersonalInformation(**yaml_data['personal_information']),
        education_details=[Education(**edu) for edu in yaml_data['education_details']],
        experience_details=[Experience(**exp) for exp in yaml_data['experience_details']],
        projects=[Project(**proj) for proj in yaml_data['projects']],
        achievements=[Achievement(**ach) for ach in yaml_data['achievements']],
        certifications=[Certification(**cert) for cert in yaml_data['certifications']],
        languages=[Language(**lang) for lang in yaml_data['languages']],
        interests=yaml_data['interests'],
        availability=yaml_data['availability'],
        salary_expectations=yaml_data['salary_expectations'],
        self_identification=SelfIdentification(**self_id),
        legal_authorization=WorkAuthorization(**work_auth),
        work_preferences=WorkPreferences(**work_prefs)
    )

    # Convert to dict for MongoDB
    return resume_data.model_dump()


# Updated endpoint
@router.post("/create_resume", response_description="Add new resume")
async def ingest_resume(
        yaml_data: Dict[str, Any] = Body(...),
        user_id: str = Body(...),
        db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Endpoint to ingest a new resume into the MongoDB database.
    """
    # Check if user exists in PostgreSQL
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # Convert YAML data to structured JSON
        resume_data = convert_yaml_to_resume_json(yaml_data, user_id)

        # Insert into MongoDB
        new_resume = await add_resume(resume_data)

        if "error" in new_resume:
            raise HTTPException(status_code=400, detail=new_resume["error"])

        return new_resume

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
