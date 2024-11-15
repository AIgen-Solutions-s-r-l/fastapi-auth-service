# auth_service

## Overview

**auth_service** is a FastAPI-based authentication service designed to handle user registration, login, and resume ingestion. It uses PostgreSQL for user data and MongoDB for storing resumes. The service includes the following main functionalities:

- User Registration
- User Login and JWT Authentication
- Resume Ingestion
- Resume Retrieval by User ID

## Setup

### Prerequisites

Ensure you have the following installed:
- Python 3.12.3
- pip
- PostgreSQL
- MongoDB

### Installation

1. Clone the repository:

    ```sh
    git clone https://github.com/your-repo.git
    cd your-repo
    ```

2. Create a virtual environment and activate it:

    ```sh
    python -m venv venv
    venv\Scripts\activate   # On Windows
    # or 
    source venv/bin/activate  # On macOS/Linux
    ```

3. Install the necessary packages:

    ```sh
    pip install -r requirements.txt
    ```

### Database Configuration

1. **PostgreSQL**:
    Configure your PostgreSQL database connection in `app/core/database.py`:

    ```python
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    DATABASE_URL = "postgresql+asyncpg://user:password@localhost/dbname"

    engine = create_async_engine(DATABASE_URL, future=True, echo=True)
    async_session = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def get_db() -> AsyncSession:
        async with async_session() as session:
            yield session
    ```

    Ensure your PostgreSQL server is running, and the database credentials (`user`, `password`, `localhost`, `dbname`) are correct.

2. **MongoDB**:
    Configure your MongoDB connection in `app/core/database.py`:

    ```python
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo.errors import DuplicateKeyError

    MONGO_DETAILS = "mongodb://localhost:27017"

    client = AsyncIOMotorClient(MONGO_DETAILS)
    database = client.your_database_name
    collection_name = database.get_collection("resumes")

    async def add_resume(resume: dict):
        try:
            result = await collection_name.insert_one(resume)
        except DuplicateKeyError:
            return {"error": "Resume already exists"}

        inserted_resume = await collection_name.find_one({"_id": result.inserted_id})
        return inserted_resume

    async def get_resume_by_user_id(user_id: str):
        resume = await collection_name.find_one({"user_id": user_id})
        if not resume:
            return {"error": "Resume not found"}
        return resume
    ```

    Ensure your MongoDB server is running and the connection details (`mongodb://localhost:27017`) are correct.

### Running the Application

To run the application:

```sh
uvicorn main:app --reload
```  

(note:  
$ sudo ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 80
otherwise:  
$ ./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
and as suggestion 127.0.0.1 - localhost)

### API Endpoints

#### User Registration

Register a new user at `POST /auth/register`:

```http
POST /auth/register
```

Request Body:
```json
{
    "username": "johndoe",
    "email": "johndoe@example.com",
    "password": "securepassword"
}
```

Response:
```json
{
    "message": "User registered successfully",
    "user": "johndoe"
}
```

#### User Login

Authenticate a user and obtain a JWT token at `POST /auth/login`:

```http
POST /auth/login
```

Request Body (as `application/x-www-form-urlencoded`):
```plaintext
username=johndoe
password=securepassword
```

Response:
```json
{
    "access_token": "your.jwt.token.here",
    "token_type": "bearer"
}
```

#### Get User by Username

Retrieve a user's details by username at `POST /auth/get_user_from_username`:

```http
POST /auth/get_user_from_username
```

Request Body:
```json
{
    "username": "johndoe"
}
```

Response:
```json
{
    "id": 1,
    "username": "johndoe",
    "email": "johndoe@example.com",
    "hashed_password": "hashedpassword"
    // other user details
}
```

### Resume Ingestor Endpoints

#### Ingest Resume

Ingest a user's resume at `POST /resume_ingestor/ingest_resume`:

```http
POST /resume_ingestor/ingest_resume
```

Request Body:
```json
{
    "user_id": "user123",
    "resume": {
        "name": "John Doe",
        "email": "johndoe@example.com",
        "experience": [{"title": "Software Developer", "company": "Example Corp", "years": 2}],
        "education": [{"degree": "BSc Computer Science", "institution": "University XYZ", "years": 4}],
        "skills": ["Python", "FastAPI", "MongoDB"]
    }
}
```

Response:
```json
{
    "message": "Resume ingested successfully",
    "resume_id": "resume789"
}
```

#### Get Resume by User ID

Retrieve a user's resume by user ID at `GET /resume_ingestor/resume/{user_id}`:

```http
GET /resume_ingestor/resume/{user_id}
```

Response:
```json
{
    "user_id": "user123",
    "name": "John Doe",
    "email": "johndoe@example.com",
    "experience": [{"title": "Software Developer", "company": "Example Corp", "years": 2}],
    "education": [{"degree": "BSc Computer Science", "institution": "University XYZ", "years": 4}],
    "skills": ["Python", "FastAPI", "MongoDB"]
}
```

---

Let me know if you have any questions or need further assistance!