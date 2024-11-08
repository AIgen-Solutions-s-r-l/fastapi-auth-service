from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any
from mongodb import add_resume, get_resume_by_user_id
from db import get_db
from models import User

router = APIRouter()


class Resume(BaseModel):
    user_id: str
    name: str
    email: str
    experience: Any  # Replace with appropriate type or another Pydantic model if necessary
    education: Any  # Replace with appropriate type or another Pydantic model if necessary
    skills: list


@router.post("/create_resume", response_description="Add new resume")
async def ingest_resume(resume: Resume = Body(...), db: AsyncSession = Depends(get_db)):
    # Verify if user exists in PostgreSQL
    user = await db.get(User, resume.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    resume = resume.dict()
    new_resume = await add_resume(resume)
    if "error" in new_resume:
        raise HTTPException(status_code=400, detail=new_resume["error"])
    return new_resume


@router.get("/resume/{user_id}", response_description="Get resume by user ID")
async def get_resume(user_id: str):
    resume = await get_resume_by_user_id(user_id)
    if "error" in resume:
        raise HTTPException(status_code=404, detail=resume["error"])
    return resume
