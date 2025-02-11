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

## API Endpoints

### Authentication Headers

For protected endpoints, include the JWT token in the Authorization header:
```http
Authorization: Bearer <your-jwt-token>
```

### Rate Limiting

All endpoints are rate-limited to prevent abuse:
- 100 requests per minute for authentication endpoints
- 1000 requests per minute for other endpoints
- Rate limits are per IP address

### 1. User Registration

```http
POST /auth/register
Content-Type: application/json

{
    "username": "johndoe",
    "email": "johndoe@example.com",
    "password": "securepassword"
}

Response (201 Created):
{
    "message": "User registered successfully",
    "username": "johndoe",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
}

Possible Status Codes:
- 201: Successfully registered
- 409: Username or email already exists
- 422: Validation error (invalid email format, password too short)
```

### 2. User Login

```http
POST /auth/login
Content-Type: application/x-www-form-urlencoded

username=johndoe&password=securepassword

Response (200 OK):
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
}

Possible Status Codes:
- 200: Successfully authenticated
- 401: Invalid credentials
- 422: Validation error
```

### 3. Get User Profile

```http
GET /auth/me
Authorization: Bearer <jwt-token>

Response (200 OK):
{
    "username": "johndoe",
    "email": "johndoe@example.com"
}

Optional Query Parameters:
- user_id: (Admin only) Get another user's profile

Possible Status Codes:
- 200: Profile retrieved successfully
- 401: Not authenticated
- 403: Not authorized (when non-admin tries to access other profiles)
- 404: User not found
```

### 4. Password Reset Request

```http
POST /auth/password-reset-request
Content-Type: application/json

{
    "email": "johndoe@example.com"
}

Response (200 OK):
{
    "message": "Password reset link sent to email if account exists"
}

Note: Always returns 200 OK to prevent email enumeration
```

### 5. Reset Password

```http
POST /auth/reset-password
Content-Type: application/json

{
    "token": "reset-token-from-email",
    "new_password": "newSecurePassword"
}

Response (200 OK):
{
    "message": "Password has been reset successfully"
}

Possible Status Codes:
- 200: Password reset successful
- 400: Invalid or expired reset token
- 422: Validation error (password requirements not met)
```

### 6. Change Password

```http
PUT /auth/users/{username}/password
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
    "current_password": "currentPassword",
    "new_password": "newSecurePassword"
}

Response (200 OK):
{
    "message": "Password updated successfully"
}

Possible Status Codes:
- 200: Password changed successfully
- 401: Invalid current password
- 404: User not found
- 422: Validation error
```

### 7. Change Email

```http
PUT /auth/users/{username}/email
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
    "new_email": "newemail@example.com",
    "current_password": "currentPassword"
}

Response (200 OK):
{
    "message": "Email updated successfully",
    "username": "username",
    "email": "newemail@example.com"
}

Possible Status Codes:
- 200: Email changed successfully
- 400: Email already registered
- 401: Invalid password or unauthorized
- 403: Not authorized to change other users' email
- 404: User not found
- 422: Invalid email format
```


### 8. Delete Account

```http
DELETE /auth/users/{username}
Authorization: Bearer <jwt-token>

Query Parameters:
password: Current password for verification

Response (200 OK):
{
    "message": "User deleted successfully"
}

Possible Status Codes:
- 200: Account deleted successfully
- 401: Invalid password
- 404: User not found
```

### 8. Refresh Token

```http
POST /auth/refresh
Content-Type: application/json

{
    "token": "existing-jwt-token"
}

Response (200 OK):
{
    "access_token": "new-jwt-token",
    "token_type": "bearer"
}

Possible Status Codes:
- 200: Token refreshed successfully
- 401: Invalid or expired token
```

### 9. Logout

```http
POST /auth/logout
Authorization: Bearer <jwt-token>

Response (200 OK):
{
    "message": "Successfully logged out"
}

Note: Client should handle token removal from storage
```

### 10. Get User Details

```http
GET /auth/users/{username}
Authorization: Bearer <jwt-token>

Response (200 OK):
{
    "username": "johndoe",
    "email": "johndoe@example.com",
    "id": 1,
    "is_admin": false
}

Possible Status Codes:
- 200: User details retrieved successfully
- 404: User not found
```

### 11. Get Credit Balance

```http
GET /credits/balance
Authorization: Bearer <jwt-token>

Response (200 OK):
{
    "user_id": 1,
    "balance": 100.50,
    "updated_at": "2025-02-06T17:00:00Z"
}

Possible Status Codes:
- 200: Balance retrieved successfully
- 401: Not authenticated
```

### 12. Add Credits

```http
POST /credits/add
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
    "amount": 50.00,
    "reference_id": "order_123",  // Optional
    "description": "Credit purchase"  // Optional
}

Response (200 OK):
{
    "id": 1,
    "user_id": 1,
    "amount": 50.00,
    "transaction_type": "credit_added",
    "reference_id": "order_123",
    "description": "Credit purchase",
    "created_at": "2025-02-06T17:00:00Z",
    "new_balance": 150.50
}

Possible Status Codes:
- 200: Credits added successfully
- 401: Not authenticated
- 422: Validation error (invalid amount)
```

### 13. Use Credits

```http
POST /credits/use
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
    "amount": 25.00,
    "reference_id": "purchase_456",  // Optional
    "description": "Service purchase"  // Optional
}

Response (200 OK):
{
    "id": 2,
    "user_id": 1,
    "amount": 25.00,
    "transaction_type": "credit_used",
    "reference_id": "purchase_456",
    "description": "Service purchase",
    "created_at": "2025-02-06T17:05:00Z",
    "new_balance": 125.50
}

Possible Status Codes:
- 200: Credits used successfully
- 400: Insufficient credits
- 401: Not authenticated
- 422: Validation error (invalid amount)
```

### 14. Get Transaction History

```http
GET /credits/transactions
Authorization: Bearer <jwt-token>

Query Parameters:
- skip: Number of records to skip (default: 0)
- limit: Maximum number of records to return (default: 50)

Response (200 OK):
{
    "transactions": [
        {
            "id": 2,
            "user_id": 1,
            "amount": 25.00,
            "transaction_type": "credit_used",
            "reference_id": "purchase_456",
            "description": "Service purchase",
            "created_at": "2025-02-06T17:05:00Z",
            "new_balance": 125.50
        },
        {
            "id": 1,
            "user_id": 1,
            "amount": 50.00,
            "transaction_type": "credit_added",
            "reference_id": "order_123",
            "description": "Credit purchase",
            "created_at": "2025-02-06T17:00:00Z",
            "new_balance": 150.50
        }
    ],
    "total_count": 2
}

Possible Status Codes:
- 200: Transaction history retrieved successfully
- 401: Not authenticated
```

## Key Features

- **User Authentication**
  - Secure user registration and login
  - JWT-based authentication with configurable expiration
  - Password reset functionality with email integration
  - bcrypt password hashing

- **Credit System**
  - Secure credit balance management
  - Transaction history tracking
  - Credit addition and usage operations
  - Atomic transactions for data consistency
  - Detailed audit logging
  - Protection against negative balances
  - Transaction reference tracking

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

## Database Migrations

The service uses Alembic for database migrations. Migrations are automatically handled during container startup in production, but you can also manage them manually during development.

### Development Migration Commands

1. Create a new migration:
   ```sh
   alembic revision --autogenerate -m "description of changes"
   ```

2. Apply all pending migrations:
   ```sh
   alembic upgrade head
   ```

3. Rollback the last migration:
   ```sh
   alembic downgrade -1
   ```

4. View migration history:
   ```sh
   alembic history
   ```

5. View current migration state:
   ```sh
   alembic current
   ```

### Production Deployment

In production (Kubernetes deployment), migrations are automatically handled during container startup. The process:

1. Waits for the database to be available
2. Runs all pending migrations before starting the application
3. Fails fast if migrations cannot be applied, preventing the pod from starting with an inconsistent database state

### Migration Best Practices

1. Always review autogenerated migrations before applying them
2. Test migrations on a copy of production data before deploying
3. Include both upgrade and downgrade paths in migrations
4. Keep migrations reversible when possible
5. Run migrations before deploying new application code

## Running the Application

### Development Mode
```sh
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

### Production Mode
```sh
uvicorn app.main:app --host 0.0.0.0 --port 80
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
    ├── test_auth_router.py # Authentication endpoint tests
    └── test_credit_router.py # Credit system endpoint tests
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
   - `credit.py`: Defines credit-related models:
     - UserCredit: Stores user credit balances
     - CreditTransaction: Tracks all credit operations with detailed history
     - TransactionType: Enumerates transaction types (purchase, credit_added, credit_used, etc.)

3. **Routers** (`app/routers/`)
   - `auth_router.py`: Implements endpoints for:
     - User registration and login
     - Password management
     - Token refresh
     - Account deletion
   - `credit_router.py`: Implements endpoints for:
     - Credit balance management
     - Adding and using credits
     - Transaction history
     - Balance queries

4. **Services** (`app/services/`)
   - `user_service.py`: Implements business logic for:
     - User authentication flows
     - Password hashing and verification
     - Email notifications
     - Database operations
   - `credit_service.py`: Implements business logic for:
     - Credit balance management
     - Transaction processing
     - Balance validation
     - Transaction history tracking

5. **Schemas** (`app/schemas/`)
   - `auth_schemas.py`: Defines Pydantic models for:
     - Request validation
     - Response serialization
     - Data transformation
   - `credit_schemas.py`: Defines Pydantic models for:
     - Credit operation requests
     - Transaction responses
     - Balance queries
     - Transaction history

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
