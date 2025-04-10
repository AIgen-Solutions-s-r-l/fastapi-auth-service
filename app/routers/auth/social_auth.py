"""Router module for social authentication endpoints."""

from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth_schemas import (
    GoogleAuthRequest, GoogleAuthCallback, AccountLinkRequest, Token
)
from app.services.oauth_service import GoogleOAuthService
from app.services.user_service import UserService
from app.models.user import User
from app.core.auth import get_current_active_user
from app.log.logging import logger

router = APIRouter()

@router.post(
    "/google-auth",
    response_model=Dict[str, str],
    responses={
        200: {"description": "Google authorization URL generated"},
        500: {"description": "Error generating authorization URL"}
    }
)
async def google_auth(
    request: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Get Google OAuth authorization URL.
    
    Args:
        request: Optional redirect URI
        db: Database session
        
    Returns:
        Dict with authorization URL
    """
    try:
        oauth_service = GoogleOAuthService(db)
        auth_url = await oauth_service.get_authorization_url(request.redirect_uri)
        
        logger.info(
            "Generated Google auth URL",
            event_type="google_auth_url_generated",
            redirect_uri=request.redirect_uri
        )
        
        return {"authorization_url": auth_url}
    except Exception as e:
        logger.error(
            "Error generating Google auth URL",
            event_type="google_auth_url_error",
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating authorization URL"
        )

# POST endpoint for Google callback removed as we only need the GET endpoint

@router.post(
    "/link-google-account",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Google account linked successfully"},
        400: {"description": "Invalid code or account already linked"},
        401: {"description": "Invalid password"}
    }
)
async def link_google_account(
    request: AccountLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Link Google account to existing user.
    
    Args:
        request: Google auth code and current password
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Dict with success message
    """
    try:
        # Verify password first
        user_service = UserService(db)
        user = await user_service.authenticate_user(current_user.email, request.password)
        
        if not user:
            logger.warning(
                "Invalid password for account linking",
                event_type="account_linking_error",
                user_id=current_user.id,
                email=current_user.email,
                error="invalid_password"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )
            
        # Get Google profile
        oauth_service = GoogleOAuthService(db)
        tokens = await oauth_service.exchange_code_for_tokens(request.code)
        profile = await oauth_service.get_user_profile(tokens['access_token'])
        
        # Check if profile email matches user email
        if profile.get('email') != current_user.email:
            logger.warning(
                "Email mismatch for account linking",
                event_type="account_linking_error",
                user_id=current_user.id,
                user_email=current_user.email,
                google_email=profile.get('email'),
                error="email_mismatch"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email does not match your current email"
            )
            
        # Link account
        updated_user = await oauth_service.link_google_account(current_user, profile)
        
        logger.info(
            "Google account linked successfully",
            event_type="google_account_linked",
            user_id=current_user.id,
            email=current_user.email,
            google_id=profile.get('sub')
        )
        
        return {
            "message": "Google account linked successfully",
            "email": updated_user.email,
            "auth_type": updated_user.auth_type
        }
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error(
            "Error linking Google account",
            event_type="account_linking_error",
            user_id=current_user.id,
            email=current_user.email,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to link Google account"
        )

@router.post(
    "/unlink-google-account",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Google account unlinked successfully"},
        400: {"description": "Cannot unlink without password"}
    }
)
async def unlink_google_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Unlink Google account from user.
    
    Args:
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Dict with success message
    """
    try:
        # Check if user has Google account linked
        if not current_user.google_id:
            return {
                "message": "No Google account linked to this user",
                "auth_type": current_user.auth_type
            }
            
        # Unlink account
        oauth_service = GoogleOAuthService(db)
        updated_user = await oauth_service.unlink_google_account(current_user)
        
        logger.info(
            "Google account unlinked successfully",
            event_type="google_account_unlinked",
            user_id=current_user.id,
            email=current_user.email
        )
        
        return {
            "message": "Google account unlinked successfully",
            "email": updated_user.email,
            "auth_type": updated_user.auth_type
        }
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error(
            "Error unlinking Google account",
            event_type="account_unlinking_error",
            user_id=current_user.id,
            email=current_user.email,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to unlink Google account"
        )

@router.get(
    "/google-callback",
    responses={
        302: {"description": "Redirect to frontend with code"},
        400: {"description": "Error in Google OAuth flow"}
    }
)
async def google_callback_redirect(
    code: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Google OAuth callback redirect.
    This endpoint receives the redirect from Google OAuth and redirects to the frontend
    with the authorization code or error.
    
    Args:
        code: Authorization code from Google
        error: Error from Google OAuth
        db: Database session
        
    Returns:
        Redirect to frontend
    """
    from fastapi.responses import RedirectResponse
    from app.core.config import settings
    
    # Frontend URL to redirect to
    frontend_url = f"{settings.FRONTEND_URL}/api/auth/callback"
    
    # If there's an error, redirect to frontend with error
    if error:
        logger.error(
            "Error in Google OAuth flow",
            event_type="google_oauth_error",
            error=error
        )
        return RedirectResponse(f"{frontend_url}?error={error}")
    
    # If no code, redirect to frontend with error
    if not code:
        logger.error(
            "No code provided in Google OAuth callback",
            event_type="google_oauth_error"
        )
        return RedirectResponse(f"{frontend_url}?error=no_code")
    
    # Redirect to frontend with code
    return RedirectResponse(f"{frontend_url}?code={code}")

@router.post(
   "/login-with-google",
   response_model=Token,
   responses={
       200: {"description": "Successfully authenticated with Google"},
       400: {"description": "Invalid or expired code"}
   }
)
async def login_with_google(
   callback: GoogleAuthCallback,
   db: AsyncSession = Depends(get_db)
) -> Token:
   """
   Handle Google OAuth login.
   
   Args:
       callback: Authorization code from Google
       db: Database session
       
   Returns:
       Token: JWT access token
   """
   try:
       oauth_service = GoogleOAuthService(db)
       user, access_token = await oauth_service.login_with_google(callback.code)
       
       logger.info(
           "Google OAuth login successful",
           event_type="google_oauth_login",
           user_id=user.id,
           email=user.email
       )
       
       return Token(access_token=access_token, token_type="bearer")
   except HTTPException as http_ex:
       # Re-raise HTTP exceptions
       raise http_ex
   except Exception as e:
       logger.error(
           "Google OAuth login error",
           event_type="google_oauth_login_error",
           error_type=type(e).__name__,
           error_details=str(e)
       )
       raise HTTPException(
           status_code=status.HTTP_400_BAD_REQUEST,
           detail="Failed to authenticate with Google"
       )