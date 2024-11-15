# app/core/base.py
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Import all models
from app.models.user import User