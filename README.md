# 🔐 auth_service

[![FastAPI](https://img.shields.io/badge/FastAPI-0.95.0-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-13+-336791.svg?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![JWT](https://img.shields.io/badge/JWT-Auth-000000.svg?style=flat&logo=json-web-tokens&logoColor=white)](https://jwt.io)

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture and Implementation](#-architecture-and-implementation)
  - [Authentication Flow](#authentication-flow)
  - [Security Implementation](#security-implementation)
  - [Error Handling](#error-handling)
- [API Endpoints](#-api-endpoints)
  - [Authentication Headers](#authentication-headers)
  - [Endpoint Security Classification](#endpoint-security-classification)
  - [Rate Limiting](#rate-limiting)
- [Key Features](#-key-features)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Database Migrations](#-database-migrations)
- [Running the Application](#-running-the-application)
- [Development Tools](#-development-tools)
- [Testing](#-testing)
- [Project Structure](#-project-structure)
- [Error Handling](#-error-handling)
- [Logging](#-logging)
- [Contributing](#-contributing)
- [License](#-license)

## 🚀 Overview

**auth_service** is a production-ready FastAPI-based authentication service designed to handle user authentication and management. It uses PostgreSQL for storing user data and provides secure JWT-based authentication with comprehensive logging and monitoring capabilities.

> 💡 **Key Strengths**: Scalable architecture, robust security, and comprehensive API for seamless integration with other services.

## 🏗️ Architecture and Implementation

The auth_service follows a layered architecture pattern with clear separation of concerns:

```mermaid
graph TD
    subgraph "Client Layer"
        A[External Clients]
    end
    
    subgraph "API Layer"
        B[FastAPI Endpoints]
    end
    
    subgraph "Service Layer"
        C[Business Logic]
    end
    
    subgraph "Data Layer"
        D[PostgreSQL Database]
    end
    
    A <--> B
    B <--> C
    C <--> D
    
    style A fill:#f9f,stroke:#333,stroke-width:2px
    style B fill:#bbf,stroke:#333,stroke-width:2px
    style C fill:#bfb,stroke:#333,stroke-width:2px
    style D fill:#fbb,stroke:#333,stroke-width:2px
```

### Authentication Flow

1. **🔑 Registration Flow**
   - User submits username, email, and password
   - System checks for existing username/email
   - Password is hashed using bcrypt
   - User record is created in database
   - JWT token is generated and returned for immediate authentication
   - Welcome email is sent to user

2. **🔓 Login Flow**
   - User submits username and password
   - System verifies credentials against database
   - On success, generates JWT token with:
     - User ID
     - Username
     - Admin status
     - Expiration time (60 minutes)
   - Returns token for subsequent authenticated requests

3. **🔄 Token Refresh Flow**
   - Client submits existing JWT token
   - System verifies token validity and user existence
   - On success, generates new JWT token with:
     - Same user claims (ID, username, admin status)
     - New expiration time (60 minutes)
   - Returns new token for continued authentication

4. **🔐 Password Reset Flow**
   - User requests password reset with email
   - System generates secure reset token (JWT)
   - Reset link is sent to user's email
   - User submits new password with reset token
   - System verifies token and updates password
   - All existing reset tokens are invalidated

### Security Implementation

1. **🔒 Password Security**
   - Passwords are hashed using bcrypt with automatic salt generation
   - Salt is generated uniquely for each password and stored with hash
   - Constant-time comparison for password verification prevents timing attacks
   - Passwords never stored in plaintext or logs

2. **🔖 JWT Implementation**
   - Tokens are signed using HS256 algorithm with secure secret key
   - Include essential user claims (ID, username, admin status)
   - Configurable expiration time with automatic refresh mechanism
   - Timezone-aware token expiration handling
   - JWT validation checks signature, expiration, and user existence

3. **🛡️ Multi-Layered Endpoint Security**
   The auth_service implements a comprehensive security classification system:

   ```mermaid
   graph TD
       A[Request] --> B{Authentication<br>Required?}
       B -->|No| C[Public Access]
       B -->|Yes| D{Auth Type?}
       D -->|JWT Token| E[User Authentication]
       D -->|API Key| F[Internal Service Authentication]
       E --> G{Email<br>Verified?}
       G -->|No| H[Authenticated User]
       G -->|Yes| I[Verified User]
       F --> J[Internal Service]
       
       style A fill:#f9f9f9,stroke:#333,stroke-width:2px
       style B fill:#ffeeee,stroke:#333,stroke-width:2px
       style C fill:#eeffee,stroke:#333,stroke-width:2px
       style D fill:#ffeeee,stroke:#333,stroke-width:2px
       style E fill:#eeeeff,stroke:#333,stroke-width:2px
       style F fill:#eeeeff,stroke:#333,stroke-width:2px
       style G fill:#ffeeee,stroke:#333,stroke-width:2px
       style H fill:#eeffee,stroke:#333,stroke-width:2px
       style I fill:#eeffee,stroke:#333,stroke-width:2px
       style J fill:#eeffee,stroke:#333,stroke-width:2px
   ```

   - **🌐 Public Endpoints**: Open access to anyone, no authentication required
     - Examples: login, register, password reset, email verification
     - No security credentials needed to access these endpoints
   
   - **🔑 Authenticated Endpoints**: Require valid JWT token (authentication)
     - Examples: token refresh
     - Protected by `get_current_user` dependency
     - Checks: Bearer token present, JWT valid, user exists in database
   
   - **✓ Verified User Endpoints**: Require valid JWT token AND email verification
     - Examples: account management, profile editing, Google account linking
     - Protected by `get_current_active_user` dependency
     - Checks: All authentication checks PLUS email verification status
     - Returns 403 Forbidden if email not verified
   
   - **🔒 Internal Service Endpoints**: Require API key authentication
     - Examples: credit system endpoints, Stripe webhook handlers
     - Protected by `get_internal_service` dependency
     - Not accessible externally
     - Validates API key from X-API-Key header

4. **🔐 Security Dependencies**
   
   a. **JWT Authentication Flow**
   ```mermaid
   flowchart TD
       A[Request with JWT] --> B[Extract Bearer token from<br>Authorization header]
       B --> C{Token present?}
       C -->|No| D[401 Unauthorized]
       C -->|Yes| E[Decode JWT]
       E --> F{Token valid?}
       F -->|No| G[401 Unauthorized]
       F -->|Yes| H[Extract user_id from payload]
       H --> I[Query database for user]
       I --> J{User exists?}
       J -->|No| K[401 Unauthorized]
       J -->|Yes| L[Return User model]
       
       style A fill:#f9f9f9,stroke:#333,stroke-width:2px
       style B fill:#eeeeff,stroke:#333,stroke-width:2px
       style C fill:#ffeeee,stroke:#333,stroke-width:2px
       style D fill:#ffdddd,stroke:#333,stroke-width:2px
       style E fill:#eeeeff,stroke:#333,stroke-width:2px
       style F fill:#ffeeee,stroke:#333,stroke-width:2px
       style G fill:#ffdddd,stroke:#333,stroke-width:2px
       style H fill:#eeeeff,stroke:#333,stroke-width:2px
       style I fill:#eeeeff,stroke:#333,stroke-width:2px
       style J fill:#ffeeee,stroke:#333,stroke-width:2px
       style K fill:#ffdddd,stroke:#333,stroke-width:2px
       style L fill:#eeffee,stroke:#333,stroke-width:2px
   ```
   
   b. **Email Verification Check**
   ```mermaid
   flowchart TD
       A[get_current_active_user] --> B[get_current_user]
       B --> C[JWT Validation]
       C --> D[Return User]
       D --> E{User.is_verified?}
       E -->|Yes| F[Return Verified User]
       E -->|No| G[403 Forbidden:<br>Email not verified]
       
       style A fill:#f9f9f9,stroke:#333,stroke-width:2px
       style B fill:#eeeeff,stroke:#333,stroke-width:2px
       style C fill:#eeeeff,stroke:#333,stroke-width:2px
       style D fill:#eeeeff,stroke:#333,stroke-width:2px
       style E fill:#ffeeee,stroke:#333,stroke-width:2px
       style F fill:#eeffee,stroke:#333,stroke-width:2px
       style G fill:#ffdddd,stroke:#333,stroke-width:2px
   ```
   
   c. **Internal Service Authentication Flow**
   ```mermaid
   flowchart TD
       A[Request to internal endpoint] --> B[Extract API key from<br>X-API-Key header]
       B --> C{API key present?}
       C -->|No| D[401 Unauthorized]
       C -->|Yes| E{API key == configured key?}
       E -->|No| F[401 Unauthorized]
       E -->|Yes| G[Allow access to<br>internal endpoint]
       
       style A fill:#f9f9f9,stroke:#333,stroke-width:2px
       style B fill:#eeeeff,stroke:#333,stroke-width:2px
       style C fill:#ffeeee,stroke:#333,stroke-width:2px
       style D fill:#ffdddd,stroke:#333,stroke-width:2px
       style E fill:#ffeeee,stroke:#333,stroke-width:2px
       style F fill:#ffdddd,stroke:#333,stroke-width:2px
       style G fill:#eeffee,stroke:#333,stroke-width:2px
   ```
   
   - `get_current_user`: Validates JWT token, confirms user exists (authentication only)
   - `get_current_active_user`: Validates JWT token, confirms user exists AND email is verified
   - `get_internal_service`: Validates API key for internal service access

5. **🛢️ Database Security**
   - Async PostgreSQL connections with connection pooling
   - Prepared statements for SQL injection prevention
   - Transaction management with rollback capability for data integrity
   - Connection pooling for performance optimization
   - Database credentials stored securely in environment variables

### Error Handling

The service implements comprehensive error handling with custom exceptions:

1. **🔐 Authentication Errors**
   - `InvalidCredentialsError`: Wrong username/password
   - `UserNotFoundError`: User doesn't exist
   - `UserAlreadyExistsError`: Duplicate registration

2. **🛢️ Database Errors**
   - `DatabaseOperationError`: Database transaction failures
   - `ConnectionError`: Database connectivity issues

3. **🔖 Token Errors**
   - `TokenExpiredError`: JWT token has expired
   - `InvalidTokenError`: Token validation failed

All errors are logged with context for debugging and monitoring.

## 🔌 API Endpoints

### Authentication Headers

For protected endpoints, include the JWT token in the Authorization header:
```http
Authorization: Bearer <your-jwt-token>
```

### Endpoint Security Classification

The auth_service implements a comprehensive multi-layered security model with endpoints classified into four distinct security levels:

#### Security Level Definitions:

- **🌐 Public**: No authentication required, open access to anyone
- **🔑 Authenticated**: Requires valid JWT token, accessible to any authenticated user
- **✓ Verified User**: Requires valid JWT token AND email verification
- **🔒 Internal Service**: Requires valid API key, used for service-to-service communication

#### Detailed Endpoint Classification Table

| Endpoint                         | Method | Security Level      | Auth Method                | Error Codes                            | Security Implementation                   |
|----------------------------------|--------|---------------------|----------------------------|----------------------------------------|-------------------------------------------|
| **Auth Endpoints**               |        |                     |                            |                                        |                                           |
| `/auth/login`                    | POST   | 🌐 Public           | None                       | 401: Invalid credentials               | No authentication check                   |
| `/auth/register`                 | POST   | 🌐 Public           | None                       | 409: User exists                       | No authentication check                   |
| `/auth/verify-email`             | GET    | 🌐 Public           | None                       | 400: Invalid token                     | No authentication check                   |
| `/auth/resend-verification`      | POST   | 🌐 Public           | None                       | 404: User not found                    | No authentication check                   |
| `/auth/password-reset-request`   | POST   | 🌐 Public           | None                       | 200: Always returns success            | No authentication check                   |
| `/update-password`           | POST   | 🌐 Public           | None                       | 400: Invalid/expired token             | No authentication check                   |
| `/auth/oauth/google/login`       | GET    | 🌐 Public           | None                       | 302: Redirect to Google                | No authentication check                   |
| `/auth/oauth/google/callback`    | GET    | 🌐 Public           | None                       | 400: Invalid state/code                | No authentication check                   |
| `/auth/test-email`               | GET    | 🌐 Public           | None                       | 500: Email sending failed              | No authentication check                   |
| `/auth/verify-email-templates`   | GET    | 🌐 Public           | None                       | N/A                                    | No authentication check                   |
| `/auth/refresh`                  | POST   | 🔑 Authenticated    | JWT token in body          | 401: Invalid/expired token             | get_current_user dependency              |
| `/auth/me`                       | GET    | ✓ Verified User     | JWT token + verified email | 401: Invalid, 403: Unverified         | get_current_active_user dependency       |
| `/auth/logout`                   | POST   | ✓ Verified User     | JWT token + verified email | 401: Invalid, 403: Unverified         | get_current_active_user dependency       |
| `/auth/users/change-password`    | PUT    | ✓ Verified User     | JWT token + verified email | 401: Invalid, 403: Unverified         | get_current_active_user dependency       |
| `/auth/users/change-email`       | PUT    | ✓ Verified User     | JWT token + verified email | 401: Invalid, 403: Unverified         | get_current_active_user dependency       |
| `/auth/users/delete-account`     | DELETE | ✓ Verified User     | JWT token + verified email | 401: Invalid, 403: Unverified         | get_current_active_user dependency       |
| `/auth/link/google`              | POST   | ✓ Verified User     | JWT token + verified email | 401: Invalid, 403: Unverified         | get_current_active_user dependency       |
| `/auth/unlink/google`            | POST   | ✓ Verified User     | JWT token + verified email | 401: Invalid, 403: Unverified         | get_current_active_user dependency       |
| `/auth/users/{user_id}/email`    | GET    | 🔒 Internal Service | API key in X-API-Key header | 401: Invalid, 403: Unverified         | get_internal_service dependency          |
| `/auth/users/by-email/{email}`   | GET    | 🔒 Internal Service | API key in X-API-Key header | 401: Invalid, 403: Unverified         | get_internal_service dependency          |
| **Credit Endpoints**             |        |                     |                            |                                        |                                           |
| `/credits/balance`               | GET    | 🔒 Internal Service | API key in X-API-Key header| 401: Invalid/missing API key           | get_internal_service dependency          |
| `/credits/add`                   | POST   | 🔒 Internal Service | API key in X-API-Key header| 401: Invalid/missing API key           | get_internal_service dependency          |
| `/credits/use`                   | POST   | 🔒 Internal Service | API key in X-API-Key header| 401: Invalid/missing API key           | get_internal_service dependency          |
| `/credits/transactions`          | GET    | 🔒 Internal Service | API key in X-API-Key header| 401: Invalid/missing API key           | get_internal_service dependency          |
| **Stripe Endpoints**             |        |                     |                            |                                        |                                           |
| `/stripe/webhook`                | POST   | 🔒 Internal Service | API key in X-API-Key header| 401: Invalid/missing API key           | get_internal_service dependency          |
| `/stripe/create-checkout-session`| POST   | 🔒 Internal Service | API key in X-API-Key header| 401: Invalid/missing API key           | get_internal_service dependency          |
| `/stripe/setup-intent`           | POST   | 🔒 Internal Service | API key in X-API-Key header| 401: Invalid/missing API key           | get_internal_service dependency          |
| `/stripe/payment-methods`        | GET    | 🔒 Internal Service | API key in X-API-Key header| 401: Invalid/missing API key           | get_internal_service dependency          |
| `/stripe/create-subscription`    | POST   | 🔒 Internal Service | API key in X-API-Key header| 401: Invalid/missing API key           | get_internal_service dependency          |

#### Security Enforcement Workflow

For every incoming request to a protected endpoint, the authentication flow follows this pattern:

```mermaid
flowchart TB
    A[Incoming Request] --> B{Endpoint Security<br>Classification}
    
    B -->|🌐 Public| C[Process Request<br>No Auth Check]
    
    B -->|🔑 Authenticated| D[get_current_user]
    D -->|Valid JWT| E[Process Request]
    D -->|Invalid JWT| F[401 Unauthorized]
    
    B -->|✓ Verified User| G[get_current_active_user]
    G -->|Valid JWT + Verified| H[Process Request]
    G -->|Valid JWT + Unverified| I[403 Forbidden:<br>Email not verified]
    G -->|Invalid JWT| J[401 Unauthorized]
    
    B -->|🔒 Internal Service| K[get_internal_service]
    K -->|Valid API Key| L[Process Request]
    K -->|Invalid API Key| M[401 Unauthorized]
    
    style A fill:#f9f9f9,stroke:#333,stroke-width:2px
    style B fill:#ffeeee,stroke:#333,stroke-width:2px
    style C fill:#eeffee,stroke:#333,stroke-width:2px
    style D fill:#eeeeff,stroke:#333,stroke-width:2px
    style E fill:#eeffee,stroke:#333,stroke-width:2px
    style F fill:#ffdddd,stroke:#333,stroke-width:2px
    style G fill:#eeeeff,stroke:#333,stroke-width:2px
    style H fill:#eeffee,stroke:#333,stroke-width:2px
    style I fill:#ffdddd,stroke:#333,stroke-width:2px
    style J fill:#ffdddd,stroke:#333,stroke-width:2px
    style K fill:#eeeeff,stroke:#333,stroke-width:2px
    style L fill:#eeffee,stroke:#333,stroke-width:2px
    style M fill:#ffdddd,stroke:#333,stroke-width:2px
```

This multi-layered approach ensures appropriate security checks for each endpoint category, with stricter requirements for sensitive operations.

### Rate Limiting

All endpoints are rate-limited to prevent abuse:
- ⏱️ 100 requests per minute for authentication endpoints
- ⏱️ 1000 requests per minute for other endpoints
- 🌐 Rate limits are per IP address

## 🌟 Key Features

- **👤 User Authentication**
  - Secure user registration and login
  - JWT-based authentication with configurable expiration
  - Password reset functionality with email integration
  - bcrypt password hashing
  - Google OAuth integration

- **💰 Credit System**
  - Secure credit balance management
  - Transaction history tracking
  - Credit addition and usage operations
  - Atomic transactions for data consistency
  - Detailed audit logging
  - Protection against negative balances
  - Transaction reference tracking

- **📊 Advanced Logging**
  - Structured JSON logging
  - Logstash integration for centralized logging
  - Detailed error tracking with stack traces
  - Environment-specific logging configurations
  - TCP-based log shipping

- **📧 Email Integration**
  - SMTP support with SSL/TLS
  - Customizable email templates
  - Password reset email functionality
  - Configurable email settings
  - HTML email templates with responsive design

- **🛢️ Database**
  - Async PostgreSQL support with SQLAlchemy
  - Database migrations using Alembic
  - Connection pooling
  - Test database configuration
  - Transaction management

- **🔒 Security**
  - CORS middleware with configurable origins
  - Request validation
  - Structured error handling
  - Environment-based configurations
  - Multi-layered authentication

- **💳 Payment Integration**
  - Stripe integration for payment processing
  - Subscription management
  - Webhook handling for payment events
  - Secure payment method storage

## 📋 Prerequisites

- 🐍 Python 3.11 or higher
- 🐘 PostgreSQL
- 📦 Poetry (dependency management)

## 🚀 Installation

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

## ⚙️ Configuration

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

## 🔄 Database Migrations

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

1. ⏳ Waits for the database to be available
2. 🔄 Runs all pending migrations before starting the application
3. ❌ Fails fast if migrations cannot be applied, preventing the pod from starting with an inconsistent database state

### Migration Best Practices

1. 👀 Always review autogenerated migrations before applying them
2. 🧪 Test migrations on a copy of production data before deploying
3. ⬆️⬇️ Include both upgrade and downgrade paths in migrations
4. 🔄 Keep migrations reversible when possible
5. 🔄 Run migrations before deploying new application code

## 🏃‍♂️ Running the Application

### Development Mode
```sh
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

### Production Mode
```sh
uvicorn app.main:app --host 0.0.0.0 --port 80
```

## 🛠️ Development Tools

The project includes several development tools:

- **🖤 Black**: Code formatting
  ```sh
  poetry run black .
  ```

- **🔄 isort**: Import sorting
  ```sh
  poetry run isort .
  ```

- **🔍 flake8**: Code linting
  ```sh
  poetry run flake8
  ```

## 🧪 Testing

Run the test suite using pytest:

```sh
poetry run pytest
```

Or with coverage:

```sh
poetry run pytest --cov=app
```

## 📁 Project Structure

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

1. **🧩 Core Components** (`app/core/`)
   - `auth.py`: Implements JWT token generation, validation, and refresh logic
   - `config.py`: Manages environment-specific configurations using Pydantic
   - `database.py`: Handles async database connections and session management
   - `email.py`: Implements email service with templating support
   - `exceptions.py`: Defines custom exceptions for precise error handling
   - `logging_config.py`: Configures structured logging with Logstash integration

2. **📊 Models** (`app/models/`)
   - `user.py`: Defines SQLAlchemy models for:
     - User: Stores user credentials and profile
     - PasswordResetToken: Manages password reset functionality
   - `credit.py`: Defines credit-related models:
     - UserCredit: Stores user credit balances
     - CreditTransaction: Tracks all credit operations with detailed history
     - TransactionType: Enumerates transaction types (purchase, credit_added, credit_used, etc.)

3. **🔌 Routers** (`app/routers/`)
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

4. **⚙️ Services** (`app/services/`)
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

5. **📝 Schemas** (`app/schemas/`)
   - `auth_schemas.py`: Defines Pydantic models for:
     - Request validation
     - Response serialization
     - Data transformation
   - `credit_schemas.py`: Defines Pydantic models for:
     - Credit operation requests
     - Transaction responses
     - Balance queries
     - Transaction history

6. **📧 Templates** (`app/templates/`)
   - HTML email templates with support for:
     - Dynamic content injection
     - Responsive design
     - Localization support

## ❌ Error Handling

The service includes comprehensive error handling:

- ✅ Validation errors (422)
- 🔒 Authentication errors (401)
- 🚫 Authorization errors (403)
- 🔍 Not found errors (404)
- 💥 Internal server errors (500)

All errors are logged with detailed context and stack traces when applicable.

## 📊 Logging

The service implements structured logging with:

- 🖥️ Console output for development
- 📄 JSON formatting for production
- 🔄 Logstash integration for centralized logging
- 🔌 Custom TCP sink implementation
- 📝 Detailed context for each log entry
- 🐞 Error tracking with stack traces
- 🔍 Request/response logging

## 👥 Contributing

1. 🍴 Fork the repository
2. 🌿 Create a feature branch
3. 💻 Commit your changes
4. 🚀 Push to the branch
5. 🔄 Create a Pull Request

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.
