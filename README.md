# auth_service

## Overview

**auth_service** is a production-ready FastAPI-based authentication service designed to handle user authentication and management. It uses PostgreSQL for storing user data and provides secure JWT-based authentication with comprehensive logging and monitoring capabilities.

## Architecture and Implementation

### Authentication Flow

1. **Registration Flow**
   - User submits username, email, and password
   - System checks for existing username/email
   - Password is hashed using bcrypt
   - User record is created in database
   - JWT token is generated and returned for immediate authentication
   - Welcome email is sent to user

2. **Login Flow**
   - User submits username and password
   - System verifies credentials against database
   - On success, generates JWT token with:
     - User ID
     - Username
     - Admin status
     - Expiration time (60 minutes)
   - Returns token for subsequent authenticated requests

3. **Token Refresh Flow**
   - Client submits existing JWT token
   - System verifies token validity and user existence
   - On success, generates new JWT token with:
     - Same user claims (ID, username, admin status)
     - New expiration time (60 minutes)
   - Returns new token for continued authentication

4. **Password Reset Flow**
   - User requests password reset with email
   - System generates secure reset token (JWT)
   - Reset link is sent to user's email
   - User submits new password with reset token
   - System verifies token and updates password
   - All existing reset tokens are invalidated

### Security Implementation

1. **Password Security**
   - Passwords are hashed using bcrypt
   - Salt is automatically generated and stored with hash
   - Constant-time comparison for password verification

2. **JWT Implementation**
   - Tokens are signed using HS256 algorithm
   - Include user claims (ID, username, admin status)
   - Configurable expiration time
   - Timezone-aware token expiration

3. **Database Security**
   - Async PostgreSQL connections
   - Prepared statements for SQL injection prevention
   - Transaction management for data integrity
   - Connection pooling for performance

### Error Handling

The service implements comprehensive error handling with custom exceptions:

1. **Authentication Errors**
   - InvalidCredentialsError: Wrong username/password
   - UserNotFoundError: User doesn't exist
   - UserAlreadyExistsError: Duplicate registration

2. **Database Errors**
   - DatabaseOperationError: Database transaction failures
   - ConnectionError: Database connectivity issues

3. **Token Errors**
   - TokenExpiredError: JWT token has expired
   - InvalidTokenError: Token validation failed

All errors are logged with context for debugging and monitoring.

## Key Features

- **User Authentication**
  - Secure user registration and login
  - JWT-based authentication with configurable expiration
  - Password reset functionality with email integration
  - bcrypt password hashing

- **Advanced Logging**
  - Structured JSON logging
  - Logstash integration for centralized logging
  - Detailed error tracking with stack traces
  - Environment-specific logging configurations
  - TCP-based log shipping

- **Email Integration**
  - SMTP support with SSL/TLS
  - Customizable email templates
  - Password reset email functionality
  - Configurable email settings

- **Database**
  - Async PostgreSQL support with SQLAlchemy
  - Database migrations using Alembic
  - Connection pooling
  - Test database configuration

- **Security**
  - CORS middleware with configurable origins
  - Request validation
  - Structured error handling
  - Environment-based configurations

## Prerequisites

- Python 3.11 or higher
- PostgreSQL
- Poetry (dependency management)

## Installation

1. Clone the repository:
   ```sh
   git clone https://github.com/your-repo/auth_service.git
   cd auth_service
   ```

2. Install dependencies using Poetry:
   ```sh
   poetry install
   ```

   Or using pip:
   ```sh
   pip install -r requirements.txt
   ```

## Configuration

The service uses environment variables for configuration. Create a `.env` file with the following settings:

### Core Settings
```env
SERVICE_NAME=authService
ENVIRONMENT=development
DEBUG=True
```

### Database Settings
```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/main_db
TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/test_db
```

### Authentication Settings
```env
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Email Settings
```env
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-email-password
MAIL_FROM=noreply@example.com
MAIL_PORT=587
MAIL_SERVER=smtp.example.com
MAIL_SSL_TLS=True
MAIL_STARTTLS=True
FRONTEND_URL=http://localhost:3000
```

### Logging Settings
```env
LOG_LEVEL=DEBUG
SYSLOG_HOST=172.17.0.1
SYSLOG_PORT=5141
JSON_LOGS=True
LOG_RETENTION=7 days
ENABLE_LOGSTASH=True
```

## Running the Application

### Development Mode
```sh
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

### Production Mode
```sh
uvicorn app.main:app --host 0.0.0.0 --port 80
```

## API Endpoints

### Health Check
```http
GET /
Response: {"message": "authService is up and running!"}
```

### Authentication

#### Register User
```http
POST /auth/register
Content-Type: application/json

{
    "username": "johndoe",
    "email": "johndoe@example.com",
    "password": "securepassword"
}
```

#### User Login
```http
POST /auth/login
Content-Type: application/x-www-form-urlencoded

username=johndoe
password=securepassword
```

#### Password Reset Request
```http
POST /auth/forgot-password
Content-Type: application/json

{
    "email": "johndoe@example.com"
}
```

#### Reset Password
```http
POST /auth/reset-password/{token}
Content-Type: application/json

{
    "new_password": "newSecurePassword"
}
```

#### Refresh Token
```http
POST /auth/refresh
Content-Type: application/json

{
    "token": "existing-jwt-token"
}

Response:
{
    "access_token": "new-jwt-token",
    "token_type": "bearer"
}
```

## Development Tools

The project includes several development tools:

- **Black**: Code formatting
  ```sh
  poetry run black .
  ```

- **isort**: Import sorting
  ```sh
  poetry run isort .
  ```

- **flake8**: Code linting
  ```sh
  poetry run flake8
  ```

## Testing

Run the test suite using pytest:

```sh
poetry run pytest
```

Or with coverage:

```sh
poetry run pytest --cov=app
```

## Project Structure

```
auth_service/
├── alembic/                # Database migrations
│   └── versions/          # Migration scripts for schema changes
├── app/
│   ├── core/              # Core functionality
│   │   ├── auth.py        # JWT handling, token generation/validation
│   │   ├── config.py      # Environment-based configuration management
│   │   ├── database.py    # Async PostgreSQL connection handling
│   │   ├── email.py       # SMTP email service integration
│   │   ├── exceptions.py  # Custom exception definitions
│   │   └── logging_config.py  # Structured logging with Logstash
│   ├── models/            # SQLAlchemy models
│   │   └── user.py        # User and PasswordResetToken models
│   ├── routers/           # API routes
│   │   └── auth_router.py # Authentication endpoint handlers
│   ├── schemas/           # Pydantic schemas
│   │   └── auth_schemas.py # Request/response validation models
│   ├── services/          # Business logic
│   │   └── user_service.py # User operations and auth flows
│   └── templates/         # Email templates
│       └── password_reset.html # Password reset email template
└── tests/                 # Test suite
    ├── conftest.py        # Test fixtures and configuration
    └── test_auth_router.py # Authentication endpoint tests
```

### Component Details

1. **Core Components** (`app/core/`)
   - `auth.py`: Implements JWT token generation, validation, and refresh logic
   - `config.py`: Manages environment-specific configurations using Pydantic
   - `database.py`: Handles async database connections and session management
   - `email.py`: Implements email service with templating support
   - `exceptions.py`: Defines custom exceptions for precise error handling
   - `logging_config.py`: Configures structured logging with Logstash integration

2. **Models** (`app/models/`)
   - `user.py`: Defines SQLAlchemy models for:
     - User: Stores user credentials and profile
     - PasswordResetToken: Manages password reset functionality

3. **Routers** (`app/routers/`)
   - `auth_router.py`: Implements endpoints for:
     - User registration and login
     - Password management
     - Token refresh
     - Account deletion

4. **Services** (`app/services/`)
   - `user_service.py`: Implements business logic for:
     - User authentication flows
     - Password hashing and verification
     - Email notifications
     - Database operations

5. **Schemas** (`app/schemas/`)
   - `auth_schemas.py`: Defines Pydantic models for:
     - Request validation
     - Response serialization
     - Data transformation

6. **Templates** (`app/templates/`)
   - HTML email templates with support for:
     - Dynamic content injection
     - Responsive design
     - Localization support

## Error Handling

The service includes comprehensive error handling:

- Validation errors (422)
- Authentication errors (401)
- Authorization errors (403)
- Not found errors (404)
- Internal server errors (500)

All errors are logged with detailed context and stack traces when applicable.

## Logging

The service implements structured logging with:

- Console output for development
- JSON formatting for production
- Logstash integration for centralized logging
- Custom TCP sink implementation
- Detailed context for each log entry
- Error tracking with stack traces
- Request/response logging

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
