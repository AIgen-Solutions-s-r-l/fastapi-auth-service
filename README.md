# auth_service

## Overview

**auth_service** is a FastAPI-based authentication service designed to handle user authentication and management. It uses PostgreSQL for storing user data and provides secure JWT-based authentication. The service includes the following main functionalities:

- User Registration
- User Login with JWT Authentication
- Password Reset Functionality
- Email Integration
- User Management

## Setup

### Prerequisites

Ensure you have the following installed:
- Python 3.12.3
- pip
- PostgreSQL

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

Configure your PostgreSQL database connection in `app/core/config.py`. The service uses SQLAlchemy with async support:

```python
SQLALCHEMY_DATABASE_URL = "postgresql+asyncpg://user:password@localhost/dbname"
```

Ensure your PostgreSQL server is running and the database credentials are correctly configured.

### Running the Application

To run the application:

```sh
# Development mode
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 80
```

### API Endpoints

#### User Registration

Register a new user:

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

Authenticate a user and obtain a JWT token:

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

#### Password Reset

Request a password reset:

```http
POST /auth/forgot-password
```

Request Body:
```json
{
    "email": "johndoe@example.com"
}
```

Reset the password using the token:

```http
POST /auth/reset-password/{token}
```

Request Body:
```json
{
    "new_password": "newSecurePassword"
}
```

### Testing

The project includes a comprehensive test suite using pytest. To run the tests:

```sh
pytest
```

### Project Structure

```
auth_service/
├── alembic/            # Database migrations
├── app/
│   ├── core/          # Core functionality
│   │   ├── auth.py    # Authentication logic
│   │   ├── config.py  # Configuration settings
│   │   └── email.py   # Email functionality
│   ├── models/        # Database models
│   ├── routers/       # API routes
│   ├── schemas/       # Pydantic schemas
│   └── services/      # Business logic
└── tests/             # Test suite
```

### Features

- Secure password hashing using bcrypt
- JWT-based authentication
- Email integration for password reset
- Async database operations
- Database migrations using Alembic
- Comprehensive test coverage
- Docker support
