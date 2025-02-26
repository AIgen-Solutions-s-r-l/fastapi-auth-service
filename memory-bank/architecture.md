# Auth Service - Detailed Architecture

## System Overview

The auth_service is a FastAPI-based authentication service with the following high-level components:

1. **API Layer**: FastAPI routes and endpoints
2. **Service Layer**: Business logic implementation
3. **Data Access Layer**: Database models and operations
4. **Schema Layer**: Data validation and serialization
5. **Core Components**: Shared utilities and configurations

## Component Interactions

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Client/User    │────▶│    API Layer    │────▶│  Service Layer  │
│                 │     │    (Routers)    │     │   (Services)    │
│                 │◀────│                 │◀────│                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐                           ┌─────────────────┐
│                 │                           │                 │
│  External       │◀─────────────────────────▶│  Data Access    │
│  Systems        │                           │  Layer (Models) │
│  (Email, etc.)  │                           │                 │
└─────────────────┘                           └─────────────────┘
```

## Data Flow

### Authentication Flow

1. **Registration Flow**:
   - Client sends registration data to `/auth/register` endpoint
   - API layer validates input using Pydantic schemas
   - Service layer checks for existing users
   - Service layer hashes password and creates user record
   - Service layer generates JWT token
   - API layer returns token and user info to client
   - Email service sends welcome email asynchronously

2. **Login Flow**:
   - Client sends credentials to `/auth/login` endpoint
   - API layer validates input
   - Service layer verifies credentials against database
   - Service layer generates JWT token
   - API layer returns token to client

3. **Token Refresh Flow**:
   - Client sends existing token to `/auth/refresh` endpoint
   - API layer validates input
   - Service layer verifies token validity
   - Service layer generates new token
   - API layer returns new token to client

### Credit System Flow

1. **Balance Check Flow**:
   - Client requests balance at `/credits/balance` endpoint
   - API layer authenticates request using JWT
   - Service layer retrieves user's credit balance
   - API layer returns balance information

2. **Add Credits Flow**:
   - Client sends credit addition request to `/credits/add` endpoint
   - API layer authenticates and validates request
   - Service layer creates transaction record
   - Service layer updates user's credit balance
   - API layer returns transaction details and new balance

3. **Use Credits Flow**:
   - Client sends credit usage request to `/credits/use` endpoint
   - API layer authenticates and validates request
   - Service layer checks if user has sufficient balance
   - Service layer creates transaction record
   - Service layer updates user's credit balance
   - API layer returns transaction details and new balance

## Component Details

### API Layer (app/routers/)

The API layer is responsible for:
- Defining API endpoints and routes
- Validating request data
- Handling HTTP-specific concerns
- Managing authentication middleware
- Returning appropriate responses

Key components:
- `auth_router.py`: Authentication endpoints
- `credit_router.py`: Credit system endpoints
- `healthcheck_router.py`: Service health monitoring

### Service Layer (app/services/)

The service layer contains the business logic and orchestrates operations:
- `user_service.py`: User management and authentication logic
- `credit_service.py`: Credit balance and transaction logic
- `email_service.py`: Email notification handling

### Data Access Layer (app/models/)

The data access layer defines database models and handles database operations:
- `user.py`: User-related database models
- `credit.py`: Credit and transaction models
- `plan.py`: Subscription plan models

### Core Components (app/core/)

Core components provide shared functionality:
- `auth.py`: JWT token handling
- `config.py`: Application configuration
- `database.py`: Database connection management
- `email.py`: Email service configuration
- `exceptions.py`: Custom exception definitions
- `security.py`: Security utilities

## Security Architecture

1. **Authentication**:
   - JWT-based token authentication
   - Bcrypt password hashing
   - Token expiration and refresh mechanism

2. **Authorization**:
   - Role-based access control (admin vs. regular users)
   - Resource ownership verification
   - Endpoint-specific permission checks

3. **Data Protection**:
   - Password hashing with bcrypt
   - Secure database connections
   - Input validation with Pydantic

## Deployment Architecture

The service is designed to be deployed in a containerized environment:
- Docker container for the application
- PostgreSQL database (external or containerized)
- Environment-based configuration
- Automatic database migrations on startup

## Monitoring and Logging

- Structured JSON logging
- Logstash integration for centralized logging
- Health check endpoints for monitoring
- Detailed error tracking with context

## Future Architecture Considerations

1. **Scalability**:
   - Stateless design allows for horizontal scaling
   - Database connection pooling for performance
   - Potential for read replicas for database scaling

2. **Resilience**:
   - Error handling and recovery mechanisms
   - Retry logic for transient failures
   - Circuit breakers for external dependencies

3. **Integration**:
   - Well-defined API for easy integration
   - Webhook support for event notifications
   - Potential for message queue integration