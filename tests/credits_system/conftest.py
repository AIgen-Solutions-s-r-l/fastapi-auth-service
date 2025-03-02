"""Test fixtures for credit system tests."""

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# The test_user fixture is now imported from the main conftest.py

@pytest.fixture
async def verified_test_user(test_user, db_session: AsyncSession):
    """Create a verified test user with authentication token by updating the verification status."""
    # Get user by email
    result = await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )
    user = result.scalar_one_or_none()
    
    # Update verification status
    if user:
        user.is_verified = True
        await db_session.commit()
    
    # Return the original test_user data (now verified)
    return test_user