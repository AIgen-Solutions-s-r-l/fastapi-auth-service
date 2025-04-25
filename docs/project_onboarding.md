# Project Onboarding - Auth Service

## Introduction

This document provides a comprehensive onboarding guide for developers working with the auth_service project. It covers the project architecture, key features, database schema, API endpoints, and getting started instructions. This guide is intended to help new team members quickly understand the project structure and start contributing effectively.

## Project Overview

The auth_service is a production-ready FastAPI-based authentication service designed to handle user authentication and management. It uses PostgreSQL for storing user data and provides secure JWT-based authentication with comprehensive logging, monitoring, and payment capabilities.

### Key Technologies

- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL 13+
- **Authentication**: JWT tokens
- **OAuth**: Google OAuth 2.0 integration
- **Payment Processing**: Stripe integration

## Architecture

The service follows a layered architecture pattern with clear separation of concerns:

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

### Component Breakdown

1. **API Layer (Routers)**
   - `app/routers/auth/auth_router.py`: Core authentication endpoints
   - `app/routers/auth/user_auth.py`: User authentication endpoints
   - `app/routers/auth/social_auth.py`: Social authentication (Google OAuth)
   - `app/routers/auth/email_management.py`: Email verification and management
   - `app/routers/auth/password_management.py`: Password reset and management

2. **Service Layer**
   - `app/services/user_service.py`: User management operations
   - `app/services/oauth_service.py`: OAuth authentication flows
   - `app/services/email_service.py`: Email sending functionality
   - `app/services/stripe_service.py`: Payment processing
   - `app/services/credit_service.py`: Credit system management

3. **Data Layer**
   - `app/models/user.py`: User data models
   - `app/models/credit.py`: Credit system models
   - `app/models/plan.py`: Subscription plan models
   - `app/core/database.py`: Database connection management

4. **Core Components**
   - `app/core/auth.py`: Authentication dependencies
   - `app/core/security.py`: Security utilities (JWT, password hashing)
   - `app/core/config.py`: Application configuration
   - `app/log/logging.py`: Structured logging

## Key Features

### 1. User Authentication

The service provides comprehensive user authentication functionality:

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Auth Service
    participant Database
    
    %% Registration Flow
    User->>Frontend: Register (email, password)
    Frontend->>Auth Service: POST /auth/register
    Auth Service->>Database: Check if user exists
    Database-->>Auth Service: User does not exist
    Auth Service->>Database: Create user (hashed password)
    Auth Service->>Auth Service: Send verification email
    Auth Service-->>Frontend: 201 Created (User registered)
    Frontend-->>User: Registration successful
    
    %% Login Flow
    User->>Frontend: Login (email, password)
    Frontend->>Auth Service: POST /auth/login
    Auth Service->>Database: Verify credentials
    Database-->>Auth Service: Credentials valid
    Auth Service->>Auth Service: Generate JWT token
    Auth Service-->>Frontend: 200 OK (JWT token)
    Frontend-->>User: Login successful
```

- Email/password registration and login
- JWT-based authentication with configurable expiration
- Password reset functionality with email verification
- bcrypt password hashing

### 2. Google OAuth Integration

The service implements a complete Google OAuth 2.0 flow:

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Auth Service
    participant Google
    
    User->>Frontend: Click "Sign in with Google"
    Frontend->>Auth Service: POST /auth/oauth/google/login
    Auth Service-->>Frontend: Google authorization URL
    Frontend->>User: Redirect to Google
    User->>Google: Authenticate and grant permissions
    Google->>Auth Service: Redirect with authorization code
    Auth Service->>Google: Exchange code for tokens
    Google-->>Auth Service: Access token, ID token
    Auth Service->>Auth Service: Find or create user
    Auth Service-->>Frontend: JWT token
    Frontend-->>User: Login successful
```

- User initiates OAuth flow via frontend
- Backend generates Google authorization URL
- User authenticates with Google
- Google redirects back with authorization code
- Backend exchanges code for tokens and user information
- Backend finds or creates user in database
- JWT token is generated (same format as password auth)

The OAuth implementation includes:
- Account linking/unlinking
- Email verification through Google
- Support for users with both password and OAuth authentication

### 3. Security Implementation

The auth_service implements a comprehensive multi-layered security model:

```mermaid
flowchart TD
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

- **Public Endpoints**: Open access to anyone, no authentication required
- **Authenticated Endpoints**: Require valid JWT token
- **Verified User Endpoints**: Require valid JWT token AND email verification
- **Internal Service Endpoints**: Require API key authentication

### 4. Additional Features

- **Credit System**: Secure credit balance management with transaction history
- **Structured Logging**: JSON logging with Logstash integration
- **Email Integration**: SMTP support with customizable templates
- **Stripe Integration**: Payment processing and subscription management
- **Rate Limiting**: Protection against abuse (100 requests/minute for auth endpoints)

## Database Schema

The User model has been updated to support OAuth authentication:

```python
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Made nullable for OAuth-only users
    google_id = Column(String(255), nullable=True, unique=True)
    auth_type = Column(String(20), default="password", nullable=False)  # "password", "google", "both"
    is_admin = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), nullable=True)
    verification_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
```

Key fields for OAuth integration:
- `google_id`: Unique identifier from Google (nullable, unique)
- `auth_type`: Authentication type ("password", "google", or "both")
- `hashed_password`: Now nullable to support OAuth-only users

## API Endpoints

### Authentication Endpoints

| Endpoint | Method | Security Level | Description |
|----------|--------|----------------|-------------|
| `/auth/login` | POST | 🌐 Public | Authenticate user and return JWT token |
| `/auth/register` | POST | 🌐 Public | Register a new user |
| `/auth/verify-email` | GET | 🌐 Public | Verify user's email address |
| `/auth/resend-verification` | POST | 🌐 Public | Resend verification email |
| `/auth/password-reset-request` | POST | 🌐 Public | Request password reset |
| `/update-password` | POST | 🌐 Public | Update password with reset token |
| `/auth/refresh` | POST | 🔑 Authenticated | Refresh JWT token |
| `/auth/me` | GET | ✓ Verified User | Get current user info |
| `/auth/logout` | POST | ✓ Verified User | Logout user |
| `/auth/users/change-password` | PUT | ✓ Verified User | Change user password |
| `/auth/users/change-email` | PUT | ✓ Verified User | Change user email |
| `/auth/users/delete-account` | DELETE | ✓ Verified User | Delete user account |

### Google OAuth Endpoints

| Endpoint | Method | Security Level | Description |
|----------|--------|----------------|-------------|
| `/auth/oauth/google/login` | GET | 🌐 Public | Get Google authorization URL |
| `/auth/oauth/google/callback` | GET | 🌐 Public | Handle Google callback |
| `/auth/login-with-google` | POST | 🌐 Public | Complete Google login |
| `/auth/link/google` | POST | ✓ Verified User | Link Google account |
| `/auth/unlink/google` | POST | ✓ Verified User | Unlink Google account |

### Internal Service Endpoints

| Endpoint | Method | Security Level | Description |
|----------|--------|----------------|-------------|
| `/auth/users/{user_id}/email` | GET | 🔒 Internal Service | Get user email by ID |
| `/auth/users/by-email/{email}` | GET | 🔒 Internal Service | Get user by email |
| `/credits/balance` | GET | 🔒 Internal Service | Get user credit balance |
| `/credits/add` | POST | 🔒 Internal Service | Add credits to user |
| `/credits/use` | POST | 🔒 Internal Service | Use credits from user |
| `/credits/transactions` | GET | 🔒 Internal Service | Get credit transactions |
| `/stripe/webhook` | POST | 🔒 Internal Service | Handle Stripe webhook |
| `/stripe/create-checkout-session` | POST | 🔒 Internal Service | Create Stripe checkout session |

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL
- Poetry (dependency management)

### Installation

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

### Configuration

Create a `.env` file with the following settings:

```env
# Core Settings
SERVICE_NAME=authService
ENVIRONMENT=development
DEBUG=True

# Database Settings
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/main_db
TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/test_db

# Authentication Settings
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Email Settings
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-email-password
MAIL_FROM=noreply@example.com
MAIL_PORT=587
MAIL_SERVER=smtp.example.com
MAIL_SSL_TLS=True
MAIL_STARTTLS=True
FRONTEND_URL=http://localhost:3000

# Google OAuth Settings
GOOGLE_CLIENT_ID=your-client-id-here
GOOGLE_CLIENT_SECRET=your-client-secret-here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
OAUTH_SCOPES=openid email profile

# Logging Settings
LOG_LEVEL=DEBUG
SYSLOG_HOST=172.17.0.1
SYSLOG_PORT=5141
JSON_LOGS=True
LOG_RETENTION=7 days
ENABLE_LOGSTASH=True
```

### Database Migrations

Run database migrations to set up the database schema:

```sh
alembic upgrade head
```

### Running the Application

Start the application in development mode:

```sh
python run_api_server.py
```

Or using uvicorn directly:

```sh
uvicorn app.main:app --reload
```

## Integration Guide

### Frontend Integration with Google OAuth

1. **Get Google Login URL**:
   ```javascript
   async function getGoogleLoginUrl() {
     const response = await fetch('http://localhost:8000/auth/oauth/google/login');
     const data = await response.json();
     return data.auth_url;
   }
   ```

2. **Redirect to Google**:
   ```javascript
   function redirectToGoogle() {
     getGoogleLoginUrl().then(url => {
       window.location.href = url;
     });
   }
   ```

3. **Handle Callback from Google**:
   ```javascript
   async function handleGoogleCallback(code) {
     const response = await fetch('http://localhost:8000/auth/login-with-google', {
       method: 'POST',
       headers: {
         'Content-Type': 'application/json',
       },
       body: JSON.stringify({ code: code })
     });
     
     const data = await response.json();
     localStorage.setItem('token', data.access_token);
     window.location.href = '/dashboard';
   }
   ```

4. **Account Linking**:
   ```javascript
   async function linkGoogleAccount(code, password) {
     const token = localStorage.getItem('token');
     
     const response = await fetch('http://localhost:8000/auth/link/google', {
       method: 'POST',
       headers: {
         'Content-Type': 'application/json',
         'Authorization': `Bearer ${token}`
       },
       body: JSON.stringify({
         code: code,
         password: password
       })
     });
     
     return await response.json();
   }
   ```

A complete example implementation is available in `examples/google_oauth_example.html`.

## Next Steps

1. **Review Documentation**:
   - Read the detailed documentation in the `docs/` directory
   - Pay special attention to `docs/google_oauth_integration.md` and `docs/authentication_flows.md`

2. **Set Up Google OAuth**:
   - Create a project in the [Google Cloud Console](https://console.cloud.google.com/)
   - Set up OAuth credentials with the correct redirect URIs
   - Configure the environment variables with your Google OAuth credentials

3. **Explore the Test Suite**:
   - Run the tests to understand the expected behavior: `pytest`
   - Review the test files in the `tests/` directory

4. **Configure Environment**:
   - Set up your development environment with the necessary environment variables
   - Configure the database connection

5. **Contribute**:
   - Follow the project's coding standards and conventions
   - Write tests for new features
   - Document your changes