# app/schemas/resume.py
from pydantic import BaseModel, EmailStr, HttpUrl, Field, ConfigDict


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
    github: str  # Changed from HttpUrl
    linkedin: str  # Changed from HttpUrl

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Project(BaseModel):
    name: str
    description: str
    link: str  # Changed from HttpUrl

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Language(BaseModel):
    language: str
    proficiency: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Achievement(BaseModel):
    name: str
    description: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Certification(BaseModel):
    name: str
    description: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Education(BaseModel):
    education_level: str
    institution: str
    field_of_study: str
    final_evaluation_grade: str
    start_date: str
    year_of_completion: str
    exam: dict

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Experience(BaseModel):
    position: str
    company: str
    employment_period: str
    location: str
    industry: str
    key_responsibilities: list
    skills_acquired: list

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


class SelfIdentification(BaseModel):
    gender: str
    pronouns: str
    veteran: bool
    disability: bool
    ethnicity: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Resume(BaseModel):
    user_id: int = Field(..., gt=0)
    personal_information: PersonalInformation
    education_details: list
    experience_details: list
    projects: list
    achievements: list
    certifications: list
    languages: list
    interests: list
    availability: dict
    salary_expectations: dict
    self_identification: SelfIdentification
    legal_authorization: WorkAuthorization
    work_preferences: WorkPreferences

    model_config = ConfigDict(arbitrary_types_allowed=True)