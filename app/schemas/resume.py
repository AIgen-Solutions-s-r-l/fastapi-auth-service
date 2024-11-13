# app/schemas/resume.py
from typing import Any

from pydantic import BaseModel, EmailStr, HttpUrl, Field, conint


class BaseModelWithUrl(BaseModel):
    """Base class for models containing HttpUrl fields"""

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        for field, value in data.items():
            if isinstance(value, HttpUrl):
                data[field] = str(value)
        return data

    class Config:
        arbitrary_types_allowed = True


class PersonalInformation(BaseModelWithUrl):
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


class Project(BaseModelWithUrl):
    name: str
    description: str
    link: HttpUrl


class Language(BaseModel):
    language: str
    proficiency: str


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
    exam: Any  # Allow any dict structure


class Experience(BaseModel):
    position: str
    company: str
    employment_period: str
    location: str
    industry: str
    key_responsibilities: Any  # Allow any list structure
    skills_acquired: Any  # Allow any list structure


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


class SelfIdentification(BaseModel):
    gender: str
    pronouns: str
    veteran: bool
    disability: bool
    ethnicity: str


class Resume(BaseModelWithUrl):
    user_id: conint(gt=0) = Field(..., description="ID of the user submitting the resume")
    personal_information: PersonalInformation
    education_details: Any  # Allow any list structure
    experience_details: Any  # Allow any list structure
    projects: Any  # Allow any list structure
    achievements: Any  # Allow any list structure
    certifications: Any  # Allow any list structure
    languages: Any  # Allow any list structure
    interests: Any  # Allow any list structure
    availability: Any  # Allow any dict structure
    salary_expectations: Any  # Allow any dict structure
    self_identification: SelfIdentification
    legal_authorization: WorkAuthorization
    work_preferences: WorkPreferences

    class Config:
        arbitrary_types_allowed = True
