"""Authentication utilities."""

from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any, Union

from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthException
from app.models.user import User
from app.services.user_service import UserService
from app.log.logging import logger

from app.core.config import settings
from app.core.security import create_access_token, verify_jwt_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from the JWT token.
    Uses email in the 'sub' claim for authentication.

    Args:
        token: JWT token
        db: Database session

    Returns:
        User: Current authenticated user

    Raises:
        AuthException: If token is invalid or user not found
    """
    credentials_exception = AuthException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
        context={"error_type": "AuthError"}
    )
    try:
        payload = verify_jwt_token(token)
        subject: str = payload.get("sub")
        if subject is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        # Create a specific exception for expired tokens with a user-friendly message
        expired_token_exception = AuthException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
            context={"error_type": "TokenExpired"}
        )
        raise expired_token_exception
    except JWTError as e:
        # Add more context to the general JWT error
        logger.debug(
            f"JWT validation error: {str(e)}",
            event_type="auth_debug",
            error_details=str(e)
        )
        raise credentials_exception

    user_service = UserService(db)
    
    # Find user by email
    user = await user_service.get_user_by_email(subject)
    
    if user is None:
        raise credentials_exception
        
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get the current active user.
    
    This dependency first authenticates the user using get_current_user,
    then checks if the user's email is verified.
    
    Args:
        current_user: The authenticated user from get_current_user
        
    Returns:
        User: Current active user
        
    Raises:
        HTTPException: If user is not verified
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user. Please verify your email address."
        )
    return current_user


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Get the current user if token is provided and valid, otherwise return None.
    
    This is useful for endpoints that can accept either user auth or service auth.
    
    Args:
        token: JWT token (optional)
        db: Database session
        
    Returns:
        Optional[User]: Current user if authenticated, None otherwise
    """
    if not token:
        return None
        
    try:
        user = await get_current_user(token=token, db=db)
        return user
    except Exception:
        return None


async def get_internal_service(
    request: Request,
    api_key: str = Header(..., description="API key for service-to-service communication")
) -> str:
    """
    Authenticate internal service based on API key.
    
    This dependency should be used for endpoints that are only accessible
    to other microservices, not directly by users.
    
    Args:
        request: FastAPI request object
        api_key: API key from request header
        
    Returns:
        str: Service identifier
        
    Raises:
        HTTPException: If API key is invalid
    """
    if not settings.INTERNAL_API_KEY:
        logger.error(
            "INTERNAL_API_KEY not configured in settings",
            event_type="config_error",
            endpoint=request.url.path
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal service authentication not configured"
        )
        
    if api_key != settings.INTERNAL_API_KEY:
        logger.warning(
            "Invalid API key attempt for internal service",
            event_type="security_violation",
            endpoint=request.url.path
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key for internal service access"
        )
    
    return "internal_service"


async def get_service_or_user(
    request: Request,
    api_key: Optional[str] = Header(None, description="API key for service-to-service communication"),
    current_user: Optional[User] = Depends(get_current_user_optional)
) -> Dict[str, Any]:
    """
    Allow either service auth or user auth during transition.
    
    This dependency is useful during the transition period where endpoints
    might be accessed both by users directly and by other services.
    
    Args:
        request: FastAPI request object
        api_key: Optional API key from request header
        current_user: Optional current user from JWT token
        
    Returns:
        Dict[str, Any]: Authentication context with type and id
        
    Raises:
        HTTPException: If neither API key nor user authentication is valid
    """
    # Check service authentication first
    if api_key:
        try:
            if api_key == settings.INTERNAL_API_KEY:
                return {"type": "service", "id": "internal_service"}
        except Exception as e:
            logger.warning(
                f"API key validation error: {str(e)}",
                event_type="auth_error",
                endpoint=request.url.path
            )
    
    # Fall back to user authentication
    if current_user:
        return {"type": "user", "id": current_user.id, "user": current_user}
    
    # Neither authentication method succeeded
    logger.warning(
        "Authentication failed for hybrid endpoint",
        event_type="auth_error",
        endpoint=request.url.path
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Either valid API key or user authentication required"
    )
    return current_user
