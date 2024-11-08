import pytest
import pytest_asyncio
from httpx import AsyncClient
from app.main import app
from app.core.database import AsyncSessionLocal, Base, engine
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

# Configura il database di test con pytest_asyncio
@pytest_asyncio.fixture(scope="function")
async def test_db():
    """
    Sets up and tears down the test database.
    Yields:
        AsyncSession: A new database session for each test.
    """
    # Create tables in the test database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Provide a session for the test
    async with AsyncSessionLocal() as session:
        yield session

    # Drop tables after the test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

# Configura un client HTTP asincrono per i test
@pytest_asyncio.fixture(scope="function")
async def client():
    """
    Provides an HTTP client for the test.
    Yields:
        AsyncClient: The test client instance.
    """
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

# Funzione di supporto per creare un utente di test
async def create_test_user(db: AsyncSession, username: str, email: str, password: str):
    """
    Helper function to create a test user directly in the database.

    Args:
        db (AsyncSession): The database session.
        username (str): The username of the test user.
        email (str): The email of the test user.
        password (str): The hashed password of the test user.
    """
    user = User(username=username, email=email, hashed_password=password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@pytest.mark.asyncio
async def test_register_user_success(client, test_db):
    """
    Test successful user registration.
    """
    payload = {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "securepassword"
    }

    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json() == {"message": "User registered successfully", "user": "testuser"}

@pytest.mark.asyncio
async def test_register_user_duplicate_username(client, test_db):
    """
    Test registration with a duplicate username.
    """
    await create_test_user(test_db, username="existinguser", email="existinguser@example.com", password="hashedpassword")

    payload = {
        "username": "existinguser",
        "email": "newuser@example.com",
        "password": "newpassword"
    }

    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json() == {"detail": "Username already exists"}

@pytest.mark.asyncio
async def test_register_user_invalid_data(client):
    """
    Test registration with missing fields in the request payload.
    """
    payload = {
        "username": "incompleteuser"
        # Missing email and password
    }

    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 422  # Unprocessable Entity (Validation Error)
