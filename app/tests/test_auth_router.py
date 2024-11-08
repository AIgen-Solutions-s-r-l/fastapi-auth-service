import pytest
import pytest_asyncio
from httpx import AsyncClient
from app.main import app
from app.core.config import Settings
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base, AsyncSessionLocal
from sqlalchemy import text

# Import settings to access test_database_url
settings = Settings()

# Print to verify the test database URL
print("Test Database URL:", settings.test_database_url)

# Create an async engine using the test database URL
test_engine = create_async_engine(settings.test_database_url, echo=True)

# Create a sessionmaker bound to the test engine with AsyncSession class
AsyncSessionLocal = sessionmaker(  # type: ignore
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


# Database setup fixture for managing test database transactions
@pytest_asyncio.fixture(scope="function")
async def test_db():
    """
    Sets up and tears down the test database.

    This fixture:
    1. Creates all necessary tables before a test.
    2. Yields a new database session (AsyncSession) for each test.
    3. Drops all tables after the test to maintain a clean state.

    Yields:
        AsyncSession: A database session for test interactions.
    """
    # Create tables in the test database
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Yield a new database session for the test
    async with AsyncSessionLocal() as session:
        yield session

    # Drop tables after the test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# HTTP client fixture for testing API endpoints asynchronously
@pytest_asyncio.fixture(scope="function")
async def client():
    """
    Provides an asynchronous HTTP client for API requests.

    This fixture:
    1. Creates an HTTP client bound to the test instance of the FastAPI application.
    2. Yields the client for making requests in each test.

    Yields:
        AsyncClient: An instance of httpx.AsyncClient for making HTTP requests.
    """
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# Helper function for creating a user directly in the test database
async def create_test_user(db: AsyncSession, username: str, email: str, password: str):
    """
    Helper function to create a test user directly in the database.

    Args:
        db (AsyncSession): The active database session.
        username (str): The username of the test user.
        email (str): The email of the test user.
        password (str): The plaintext password, which will be hashed.

    Returns:
        User: The created user object.
    """
    hashed_password = Hasher.get_password_hash(password)
    user = User(username=username, email=email, hashed_password=hashed_password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# Test to verify successful user registration
@pytest.mark.asyncio
async def test_register_user_success(client, test_db):
    """
    Test Case: Successful registration of a new user.

    Steps:
    1. Sends a registration request with valid data.
    2. Verifies the response status code is 201.
    3. Asserts the response contains a success message and the username.

    Expected Output:
    - HTTP 201 status code with a success message.
    """
    payload = {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "securepassword"
    }
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json() == {"message": "User registered successfully", "user": "testuser"}


# Test to check duplicate username registration error handling
@pytest.mark.asyncio
async def test_register_user_duplicate_username(client, test_db):
    """
    Test Case: Attempt to register a user with an existing username.

    Steps:
    1. Create a test user with the username "existinguser".
    2. Attempt to register a new user with the same username.
    3. Verifies the response status code is 400.
    4. Asserts the response contains an error message about the duplicate username.

    Expected Output:
    - HTTP 400 status code with a "Username already exists" message.
    """
    await create_test_user(test_db, "existinguser", "existinguser@example.com", "password123")
    payload = {
        "username": "existinguser",
        "email": "newuser@example.com",
        "password": "newpassword"
    }
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already exists."


# Test to check registration with invalid input data
@pytest.mark.asyncio
async def test_register_user_invalid_data(client):
    """
    Test Case: Registration attempt with invalid input data.

    Steps:
    1. Sends a registration request with invalid username, email, and password.
    2. Verifies the response status code is 422 (Unprocessable Entity).
    3. Asserts the response contains details of the validation errors.

    Expected Output:
    - HTTP 422 status code with validation error messages.
    """
    payload = {
        "username": "",  # Invalid username (empty)
        "email": "not-an-email",  # Invalid email format
        "password": "123"  # Weak password (too short or simple)
    }
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 422
    assert "errors" in response.json()


# Test for successful login of a registered user
@pytest.mark.asyncio
async def test_login_user_success(client, test_db):
    """
    Test Case: Successful login of a registered user.

    Steps:
    1. Creates a test user with a known password.
    2. Sends a login request with valid credentials.
    3. Verifies the response status code is 200.
    4. Asserts the response contains an access token and token type.

    Expected Output:
    - HTTP 200 status code with an access token in the response.
    """
    await create_test_user(test_db, "loginuser", "loginuser@example.com", "loginpassword")
    payload = {
        "username": "loginuser",
        "password": "loginpassword"
    }
    response = await client.post("/auth/login", json=payload)
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


# Test to verify error response for invalid login credentials
@pytest.mark.asyncio
async def test_login_user_invalid_credentials(client, test_db):
    """
    Test Case: Login attempt with incorrect credentials.

    Steps:
    1. Creates a test user with a known password.
    2. Sends a login request with an incorrect password.
    3. Verifies the response status code is 401.
    4. Asserts the response contains an "Invalid credentials" message.

    Expected Output:
    - HTTP 401 status code with an "Invalid credentials" error message.
    """
    await create_test_user(test_db, "validuser", "validuser@example.com", "correctpassword")
    payload = {
        "username": "validuser",
        "password": "wrongpassword"
    }
    response = await client.post("/auth/login", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials."