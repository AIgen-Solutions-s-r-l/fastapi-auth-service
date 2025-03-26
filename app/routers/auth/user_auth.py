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


@router.get("/users/{user_id}/email",
    response_model=Dict[str, str],
    include_in_schema=False,  # Hide from public API docs
    responses={
        200: {"description": "User email retrieved successfully"},
        403: {"description": "Forbidden - Internal service access only"},
        404: {"description": "User not found"}
    }
)
async def get_email_by_user_id(
    user_id: int,
    service_id: str = Depends(get_internal_service),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Get user's email by user ID.
    
    This is an internal-only endpoint for service-to-service communication.
    Requires a valid INTERNAL_API_KEY header.
    """
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            logger.warning(
                "Email retrieval failed - user not found",
                event_type="internal_endpoint_error",
                user_id=user_id,
                service_id=service_id,
                error_type="user_not_found"
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        logger.info(
            "Email retrieved by user_id",
            event_type="internal_endpoint_access",
            user_id=user_id,
            service_id=service_id
        )
        return {"email": str(user.email)}
    except HTTPException as http_ex:
        # Re-log but keep the original HTTPException status code
        logger.error(
            "Failed to retrieve email by user_id",
            event_type="internal_endpoint_error",
            user_id=user_id,
            service_id=service_id,
            error_type="HTTPException",
            error_details=str(http_ex.detail)
        )
        # Re-raise the same HTTPException to maintain the status code
        raise http_ex
    except Exception as e:
        logger.error(
            "Failed to retrieve email by user_id",
            event_type="internal_endpoint_error",
            user_id=user_id,
            service_id=service_id,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                           detail="Internal server error when retrieving user email")