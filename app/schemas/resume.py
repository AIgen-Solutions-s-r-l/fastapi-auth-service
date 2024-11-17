# app/schemas/resume.py
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, EmailStr, Field, ConfigDict


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
    github: str
    linkedin: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Exam(BaseModel):
    course_name: str
    grade: str


class Education(BaseModel):
    education_level: str
    institution: str
    field_of_study: str
    final_evaluation_grade: str
    start_date: str
    year_of_completion: str
    exam: Dict[str, str]

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Experience(BaseModel):
    position: str
    company: str
    employment_period: str
    location: str
    industry: str
    key_responsibilities: List[str]
    skills_acquired: List[str]

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Project(BaseModel):
    name: str
    description: str
    link: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Achievement(BaseModel):
    name: str
    description: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Certification(BaseModel):
    name: str
    description: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Language(BaseModel):
    language: str
    proficiency: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Availability(BaseModel):
    notice_period: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SalaryExpectations(BaseModel):
    salary_range_usd: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SelfIdentification(BaseModel):
    gender: str
    pronouns: str
    veteran: bool
    disability: bool
    ethnicity: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


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

    model_config = ConfigDict(arbitrary_types_allowed=True)


class WorkPreferences(BaseModel):
    remote_work: bool
    in_person_work: bool
    open_to_relocation: bool
    willing_to_complete_assessments: bool
    willing_to_undergo_drug_tests: bool
    willing_to_undergo_background_checks: bool

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Resume(BaseModel):
    user_id: int = Field(gt=0, description="The ID of the user who owns the resume")
    personal_information: PersonalInformation
    # Make all other fields optional with default empty lists/values
    education_details: Optional[List[Education]] = Field(default_factory=list)
    experience_details: Optional[List[Experience]] = Field(default_factory=list)
    projects: Optional[List[Project]] = Field(default_factory=list)
    achievements: Optional[List[Achievement]] = Field(default_factory=list)
    certifications: Optional[List[Certification]] = Field(default_factory=list)
    languages: Optional[List[Language]] = Field(default_factory=list)
    interests: Optional[List[str]] = Field(default_factory=list)
    availability: Optional[Availability] = None
    salary_expectations: Optional[SalaryExpectations] = None
    self_identification: Optional[SelfIdentification] = None
    legal_authorization: Optional[WorkAuthorization] = None
    work_preferences: Optional[WorkPreferences] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ResumeRequest(BaseModel):
    """Schema for resume creation/update request."""
    user_id: int = Field(gt=0, description="The ID of the user who owns the resume")
    personal_information: PersonalInformation = Field(..., description="Personal and contact information")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 123,
                "personal_information": {
                    "name": "John",
                    "surname": "Doe",
                    "date_of_birth": "1990-01-01",
                    "country": "USA",
                    "city": "New York",
                    "address": "123 Main St",
                    "phone_prefix": "+1",
                    "phone": "555-0123",
                    "email": "john.doe@example.com",
                    "github": "github.com/johndoe",
                    "linkedin": "linkedin.com/in/johndoe"
                }
            }
        }
    )


class ResumeResponse(BaseModel):
    """Schema for resume response."""
    message: str
    data: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Resume retrieved successfully",
                "data": {
                    "personal_information": {
                        "name": "John",
                        "surname": "Doe",
                        "email": "john.doe@example.com",
                        "date_of_birth": "1990-01-01",
                        "country": "USA",
                        "city": "New York",
                        "address": "123 Main St",
                        "phone_prefix": "+1",
                        "phone": "555-0123",
                        "github": "github.com/johndoe",
                        "linkedin": "linkedin.com/in/johndoe"
                    }
                }
            }
        }
    )