# Product Context

## Authentication Service

The Authentication Service is a microservice responsible for user authentication, account management, and credit management for the application ecosystem.

## Security Architecture

### Authentication & Authorization Model

The auth_service implements a multi-layered security approach:

1. **Security Classification Levels**:
   - **Public**: No authentication required
   - **Authenticated**: Requires valid JWT token
   - **Verified User**: Requires valid JWT token AND email verification
   - **Internal Service**: Requires valid API key, not externally accessible

2. **Security Enforcement Mechanisms**:
   - **JWT Authentication**: Used for user-facing endpoints
   - **API Key Authentication**: Used for internal service communication
   - **Email Verification**: Required for sensitive operations

3. **Dependency Injection**:
   - `get_current_user`: Validates JWT token, confirms user exists
   - `get_current_active_user`: Validates JWT token, confirms user exists AND email is verified
   - `get_internal_service`: Validates API key for internal service access

### Endpoint Security Classification

#### Public Endpoints
- Login, registration, email verification, password reset
- Google OAuth login and callback
- User lookup endpoints for interservice communication

#### Authenticated Endpoints
- Token refresh

#### Verified User Endpoints
- Profile management (view, update)
- Password change
- Email change
- Account deletion
- Google account linking/unlinking

#### Internal Service Endpoints
- Credit management (balance, add, use, transactions)
- Stripe integration (webhooks, checkout, payment methods)

### Security Boundaries

```
┌────────────────────────────────────────────────────────────────┐
│                       External Access                           │
└───────────────────────────────┬────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────┐
│                     Public Endpoints (No Auth)                  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Authenticated Endpoints (JWT)               │   │
│  │                                                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │        Verified User Endpoints (JWT + Email)      │   │   │
│  │  │                                                   │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│              Internal Service Endpoints (API Key)               │
│                                                                 │
│    - Credit endpoints (balance, add, use, transactions)         │
│    - Stripe endpoints (webhooks, checkout, payment)             │
└────────────────────────────────────────────────────────────────┘
```

## Key Components

### Core Components
- **auth.py**: JWT token generation, validation, security dependencies
- **config.py**: Environment-specific configurations
- **database.py**: Async database connections
- **security.py**: Password hashing, verification

### Auth Router
- Registration, login, profile management
- Password and email operations
- Google OAuth integration
- Token refresh and logout

### Credit Router (Internal Only)
- Credit balance management
- Adding and using credits
- Transaction history
- Balance queries

### Stripe Router (Internal Only)
- Webhook handling
- Checkout sessions
- Payment method management
- Subscription creation

## Data Models

### User Model
- Authentication credentials
- Profile information
- Verification status
- OAuth credentials

### Credit Models
- UserCredit: Balance information
- CreditTransaction: Transaction history
- TransactionType: Transaction categorization

## Security Considerations

1. **JWT Security**:
   - Short expiration time (60 minutes)
   - Refresh token flow
   - Secure signature algorithm (HS256)

2. **Password Security**:
   - bcrypt hashing with salt
   - Minimum password requirements
   - Password reset flow

3. **API Key Security**:
   - Long, random keys
   - Environment-based configuration
   - Header-based transmission

4. **Email Verification**:
   - Required for sensitive operations
   - Secure verification tokens
   - Expiration for verification links