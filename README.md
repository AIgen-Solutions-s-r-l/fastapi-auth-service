# Project Name

## Overview

Brief description of the project.

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
    Configure your database connection:

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

2. **MongoDB**:
    Configure your MongoDB connection:

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

### Running the Application

To run the application:

```sh
uvicorn main:app --reload
```

You can now access the endpoint to ingest resumes at `POST /resume_ingestor/ingest_resume` and get resumes by user ID at `GET /resume_ingestor/resume/{user_id}`.

### Creating User and Resume

Send a POST request to create a user and their resume at `POST /create-user/`:
NOTE: the path currently is /auth/register (not /create-user?) (auth due to the import of auth_router)

```json
{
    "username": "johndoe",
    "email": "johndoe@example.com",
    "password": "securepassword",
    "resume": {
        "name": "John Doe",
        "email": "johndoe@example.com",
        "experience": [{"title": "Software Developer", "company": "Example Corp", "years": 2}],
        "education": [{"degree": "BSc Computer Science", "institution": "University XYZ", "years": 4}],
        "skills": ["Python", "FastAPI", "MongoDB"]
    }
}
```

Retrieve the user's resume using:

```sh
GET /resume_ingestor/resume/{user_id}
```

## License

Information about the project's license.

---

Feel free to modify this template to fit your project and organization needs. Let me know if you have any questions or need further assistance!