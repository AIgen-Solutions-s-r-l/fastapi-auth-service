"""Fixtures for subscription router tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.database import get_db

@pytest.fixture
async def async_client(db: AsyncSession):
    """Create an async test client with a clean database."""
    
    async def override_get_db():
        yield db
 
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()