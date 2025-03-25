# Auth Router Refactoring: Implementation Plan

This document provides a detailed implementation plan for refactoring the auth_router.py file into multiple domain-specific modules while ensuring backward compatibility. The plan follows an incremental approach to minimize risk and allow for verification at each step.

## Prerequisites

1. Ensure all tests for auth_router.py are passing before beginning refactoring
2. Create a feature branch for this work
3. Have a good understanding of FastAPI's router includes and dependencies

## Implementation Steps

### Phase 1: Directory Structure Setup

1. Create the new directory structure:
   ```bash
   mkdir -p app/routers/auth
   touch app/routers/auth/__init__.py
   ```

2. Create the aggregator router file:
   ```bash
   touch app/routers/auth/auth_router.py
   ```

3. Create empty module files for each domain:
   ```bash
   touch app/routers/auth/user_auth.py
   touch app/routers/auth/email_verification.py
   touch app/routers/auth/password_management.py
   touch app/routers/auth/email_management.py
   touch app/routers/auth/social_auth.py
   touch app/routers/auth/auth_utils.py
   ```

### Phase 2: Module Implementation

#### Step 1: Create Base Template for Each Module

For each module, set up the basic structure with proper imports and router definition, for example:

```python
"""Router module for [specific auth domain] endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
# Add other necessary imports based on module needs

router = APIRouter()
# Define router with no prefix or tags here - these will be handled in the main aggregator
```

#### Step 2: Move Endpoints to Modules

For each endpoint, move it to the appropriate module using this process:

1. Identify all dependencies for the endpoint
2. Copy all necessary imports to the new module
3. Move the endpoint function implementation
4. Run tests to ensure the endpoint still works when included in the main router

The following table maps each endpoint to its target module:

| Endpoint | Target Module |
|----------|--------------|
| POST /login | user_auth.py |
| POST /register | user_auth.py |
| GET /verify-email | email_verification.py |
| POST /resend-verification | email_verification.py |
| PUT /users/password | password_management.py |
| GET /users/by-email/{email} | user_auth.py |
| PUT /users/change-email | email_management.py |
| GET /verify-email-change | email_management.py |
| GET /verify-email-templates | auth_utils.py |
| POST /google-auth | social_auth.py |
| POST /google-callback | social_auth.py |
| POST /link-google-account | social_auth.py |
| POST /unlink-google-account | social_auth.py |

#### Step 3: Create the Aggregator Router

Implement the main auth_router.py to include all sub-routers while maintaining existing path structure:

```python
"""Main authentication router that aggregates all auth-related endpoints."""

from fastapi import APIRouter
from app.routers.auth.user_auth import router as user_auth_router
from app.routers.auth.email_verification import router as email_verification_router
from app.routers.auth.password_management import router as password_management_router
from app.routers.auth.email_management import router as email_management_router
from app.routers.auth.social_auth import router as social_auth_router
from app.routers.auth.auth_utils import router as auth_utils_router

# Create main router with the same tags as the original auth_router.py
router = APIRouter(tags=["authentication"])

# Include all auth-related routers without path prefix to maintain existing routes
router.include_router(user_auth_router)
router.include_router(email_verification_router)
router.include_router(password_management_router)
router.include_router(email_management_router)
router.include_router(social_auth_router)
router.include_router(auth_utils_router)
```

#### Step 4: Update __init__.py for Package Exports

Make the auth package easily importable with the main router:

```python
"""Authentication package."""

from app.routers.auth.auth_router import router

__all__ = ["router"]
```

### Phase 3: Integration and Testing

#### Step 1: Backward Compatibility Path

Update app/main.py to use the new router structure while maintaining backward compatibility:

```python
# Old import (will be removed after transition)
# from app.routers.auth_router import router as auth_router

# New import (uses the refactored structure)
from app.routers.auth import router as auth_router

# The rest of the code remains unchanged
app.include_router(auth_router, prefix="/auth")
```

#### Step 2: Test Each Integration

After implementing each module and integrating it into the main router, run the tests:

```bash
# Run all auth-related tests
pytest tests/test_auth_router
```

Ensure that:
- All tests pass
- API responses are identical to before
- No new errors are introduced

#### Step 3: Manual Testing Checklist

Test the following key authentication flows manually:

- [ ] User registration
- [ ] Email verification
- [ ] User login
- [ ] Password change
- [ ] Email change and verification
- [ ] Google OAuth login

### Phase 4: Cleanup

Once all tests are passing and the refactored structure is working correctly:

1. Remove the old auth_router.py file:
   ```bash
   git rm app/routers/auth_router.py
   ```

2. Update app/main.py to use only the new import structure:
   ```python
   from app.routers.auth import router as auth_router
   ```

3. Check for any other imports of auth_router.py in the codebase and update them:
   ```bash
   grep -r "from app.routers.auth_router" app/
   ```

## Testing Strategy

To ensure comprehensive testing during the refactoring:

1. **Unit Tests**: Test each module individually
2. **Integration Tests**: Test the aggregated router functionality
3. **End-to-End Tests**: Test complete authentication flows
4. **Load Tests**: If applicable, perform load testing to ensure performance is maintained

## Rollback Plan

If issues are encountered during the refactoring:

1. Revert the changes to app/main.py to use the original auth_router.py
2. Keep both implementations temporarily if needed (old and new side by side)
3. Fix issues in the refactored modules
4. Re-test before trying integration again

## Success Criteria

The refactoring will be considered successful when:

1. All tests pass with the new structure
2. API clients experience no change in behavior
3. The code organization is improved, with each module having clear responsibility
4. No performance regression is observed

## Example: user_auth.py Implementation

The following is a complete implementation example for the user_auth.py module:

```python
"""Router module for core authentication endpoints."""

from datetime import timedelta, datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.exceptions import UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
from app.core.security import create_access_token
from app.core.auth import get_internal_service
from app.schemas.auth_schemas import LoginRequest, Token, UserCreate, UserResponse, RegistrationResponse
from app.services.user_service import UserService, authenticate_user, create_user, get_user_by_email
from app.models.user import User
from app.log.logging import logger

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

@router.post(
    "/login",
    response_model=Token,
    description="Authenticate user and return JWT token",
    responses={
        200: {"description": "Successfully authenticated"},
        401: {"description": "Invalid credentials"}
    }
)
async def login(
        credentials: LoginRequest,
        db: AsyncSession = Depends(get_db)
) -> Token:
    """Authenticate a user and return a JWT token."""
    try:
        # Only use email for authentication
        email = credentials.email
        
        user = await authenticate_user(db, email, credentials.password)
        if not user:
            logger.warning("Authentication failed", event_type="login_failed", email=email, reason="invalid_credentials")
            raise InvalidCredentialsError()
            
        # Check if user's email is verified
        if not user.is_verified:
            logger.warning("Login attempt by unverified user", event_type="login_failed", email=email, reason="unverified_user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please check your email for verification instructions."
            )

        # Calculate expiration time using timezone-aware datetime
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta

        # Use email as the subject for tokens
        access_token = create_access_token(
            data={
                "sub": user.email,
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        logger.info("User login successful", event_type="login_success", email=user.email)
        return Token(access_token=access_token, token_type="bearer")
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error("Login error", event_type="login_error", email=credentials.email, error_type=type(e).__name__, error_details=str(e))
        raise InvalidCredentialsError() from e


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegistrationResponse,
    responses={
        201: {
            "description": "User successfully registered",
            "content": {
                "application/json": {
                    "example": {
                        "message": "User registered successfully",
                        "email": "john@example.com",
                        "verification_sent": True
                    }
                }
            }
        },
        409: {"description": "Email already exists"}
    }
)
async def register_user(
        user: UserCreate,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
) -> RegistrationResponse:
    """
    Register a new user and send a verification email.

    Returns:
        RegistrationResponse containing:
        - success message
        - email
        - verification_sent status
    """
    try:
        # Create the user (initially not verified)
        new_user = await create_user(db, str(user.email), user.password)
        
        # Send verification email
        user_service = UserService(db)
        verification_sent = await user_service.send_verification_email(new_user, background_tasks)

        logger.info("User registered",
                  event_type="user_registered",
                  email=str(user.email),
                  verification_sent=verification_sent)

        return RegistrationResponse(
            message="User registered successfully. Please check your email to verify your account.",
            email=str(new_user.email),
            verification_sent=verification_sent
        )
        
    except UserAlreadyExistsError as e:
        logger.error("Registration failed",
                   event_type="registration_error",
                   email=str(user.email),
                   error_type="user_exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "User already exists", "detail": str(e)}
        ) from e


@router.get(
    "/users/by-email/{email}",
    response_model=UserResponse,
    include_in_schema=False,  # Hide from public API docs
    responses={
        200: {"description": "User details retrieved successfully"},
        403: {"description": "Forbidden - Internal service access only"},
        404: {"description": "User not found"}
    }
)
async def get_user_details(
        email: str,
        service_id: str = Depends(get_internal_service),
        db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    Retrieve user details by email.
    
    This is an internal-only endpoint for service-to-service communication.
    Requires a valid INTERNAL_API_KEY header.
    """
    try:
        user = await get_user_by_email(db, email)
        logger.info(
            "User details retrieved",
            event_type="internal_endpoint_access",
            email=email,
            service_id=service_id
        )
        if user is None:
            logger.error(
                "User object is None",
                event_type="internal_endpoint_error",
                email=email,
                service_id=service_id
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        return UserResponse(
            email=user.email,
            is_verified=user.is_verified
        )
        
    except UserNotFoundError as e:
        logger.error(
            "User lookup failed",
            event_type="internal_endpoint_error",
            email=email,
            error_type="user_not_found",
            service_id=service_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e