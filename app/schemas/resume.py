# app/schemas/resume.py
from typing import Dict, List, Optional
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
    user_id: int = Field(..., gt=0)
    personal_information: PersonalInformation
    education_details: List[Education]
    experience_details: List[Experience]
    projects: List[Project]
    achievements: List[Achievement]
    certifications: List[Certification]
    languages: List[Language]
    interests: List[str]
    availability: Availability
    salary_expectations: SalaryExpectations
    self_identification: SelfIdentification
    legal_authorization: WorkAuthorization
    work_preferences: WorkPreferences

    model_config = ConfigDict(arbitrary_types_allowed=True)