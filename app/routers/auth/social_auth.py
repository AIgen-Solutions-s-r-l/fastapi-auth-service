"""Router module for social authentication endpoints."""

from datetime import datetime, timedelta, timezone
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
    import time
    start_time = time.time()
    
    logger.debug(
        "Received request for Google auth URL",
        event_type="google_auth_url_request",
        redirect_uri=request.redirect_uri,
        client_ip=getattr(request, "client", {}).get("host", "unknown")
    )
    
    try:
        oauth_service = GoogleOAuthService(db)
        auth_url = await oauth_service.get_authorization_url(request.redirect_uri)
        
        elapsed_time = time.time() - start_time
        logger.info(
            "Generated Google auth URL",
            event_type="google_auth_url_generated",
            redirect_uri=request.redirect_uri,
            elapsed_ms=round(elapsed_time * 1000),
            has_custom_redirect=bool(request.redirect_uri)
        )
        
        return {"authorization_url": auth_url}
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(
            "Error generating Google auth URL",
            event_type="google_auth_url_error",
            error_type=type(e).__name__,
            error_details=str(e),
            redirect_uri=request.redirect_uri,
            elapsed_ms=round(elapsed_time * 1000)
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
    import time
    start_time = time.time()
    
    # Redact email for logging
    email = current_user.email
    redacted_email = email[:3] + "***" + email[email.find('@'):] if '@' in email and len(email) > 5 else "***"
    
    # Redact code for logging
    redacted_code = request.code[:4] + "..." if len(request.code) > 4 else "***"
    
    logger.debug(
        "Received request to link Google account",
        event_type="account_linking_request",
        user_id=current_user.id,
        email_domain=email[email.find('@'):] if '@' in email else None,
        code_length=len(request.code)
    )
    
    try:
        # Verify password first
        auth_start = time.time()
        user_service = UserService(db)
        user = await user_service.authenticate_user(current_user.email, request.password)
        auth_time = time.time() - auth_start
        
        if not user:
            logger.warning(
                "Invalid password for account linking",
                event_type="account_linking_error",
                user_id=current_user.id,
                email_domain=email[email.find('@'):] if '@' in email else None,
                error="invalid_password",
                auth_time_ms=round(auth_time * 1000)
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )
        
        logger.debug(
            "Password verified for account linking",
            event_type="account_linking_password_verified",
            user_id=current_user.id,
            auth_time_ms=round(auth_time * 1000)
        )
            
        # Get Google profile
        oauth_service = GoogleOAuthService(db)
        
        token_start = time.time()
        tokens = await oauth_service.exchange_code_for_tokens(request.code)
        token_time = time.time() - token_start
        
        profile_start = time.time()
        profile = await oauth_service.get_user_profile(tokens['access_token'])
        profile_time = time.time() - profile_start
        
        # Check if profile email matches user email
        google_email = profile.get('email', '')
        redacted_google_email = google_email[:3] + "***" + google_email[google_email.find('@'):] if '@' in google_email and len(google_email) > 5 else "***"
        
        if profile.get('email') != current_user.email:
            logger.warning(
                "Email mismatch for account linking",
                event_type="account_linking_error",
                user_id=current_user.id,
                user_email_domain=email[email.find('@'):] if '@' in email else None,
                google_email_domain=google_email[google_email.find('@'):] if '@' in google_email else None,
                error="email_mismatch",
                token_time_ms=round(token_time * 1000),
                profile_time_ms=round(profile_time * 1000)
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email does not match your current email"
            )
            
        # Link account
        link_start = time.time()
        updated_user = await oauth_service.link_google_account(current_user, profile)
        link_time = time.time() - link_start
        
        elapsed_time = time.time() - start_time
        logger.info(
            "Google account linked successfully",
            event_type="google_account_linked",
            user_id=current_user.id,
            email_domain=email[email.find('@'):] if '@' in email else None,
            google_id_prefix=profile.get('sub', '')[:5] if profile.get('sub') else None,
            elapsed_ms=round(elapsed_time * 1000),
            auth_time_ms=round(auth_time * 1000),
            token_time_ms=round(token_time * 1000),
            profile_time_ms=round(profile_time * 1000),
            link_time_ms=round(link_time * 1000)
        )
        
        return {
            "message": "Google account linked successfully",
            "email": updated_user.email,
            "auth_type": updated_user.auth_type
        }
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        elapsed_time = time.time() - start_time
        logger.warning(
            f"HTTP exception during account linking: {http_ex.detail}",
            event_type="account_linking_http_error",
            user_id=current_user.id,
            email_domain=email[email.find('@'):] if '@' in email else None,
            status_code=http_ex.status_code,
            detail=http_ex.detail,
            elapsed_ms=round(elapsed_time * 1000)
        )
        raise http_ex
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(
            "Error linking Google account",
            event_type="account_linking_error",
            user_id=current_user.id,
            email_domain=email[email.find('@'):] if '@' in email else None,
            error_type=type(e).__name__,
            error_details=str(e),
            elapsed_ms=round(elapsed_time * 1000),
            code_prefix=redacted_code
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
    import time
    start_time = time.time()
    
    # Redact email for logging
    email = current_user.email
    redacted_email = email[:3] + "***" + email[email.find('@'):] if '@' in email and len(email) > 5 else "***"
    
    logger.debug(
        "Received request to unlink Google account",
        event_type="account_unlinking_request",
        user_id=current_user.id,
        email_domain=email[email.find('@'):] if '@' in email else None,
        current_auth_type=current_user.auth_type,
        has_google_id=bool(current_user.google_id)
    )
    
    try:
        # Check if user has Google account linked
        if not current_user.google_id:
            logger.info(
                "No Google account linked to this user",
                event_type="account_unlinking_not_needed",
                user_id=current_user.id,
                email_domain=email[email.find('@'):] if '@' in email else None,
                auth_type=current_user.auth_type
            )
            return {
                "message": "No Google account linked to this user",
                "auth_type": current_user.auth_type
            }
            
        # Unlink account
        unlink_start = time.time()
        oauth_service = GoogleOAuthService(db)
        updated_user = await oauth_service.unlink_google_account(current_user)
        unlink_time = time.time() - unlink_start
        
        elapsed_time = time.time() - start_time
        logger.info(
            "Google account unlinked successfully",
            event_type="google_account_unlinked",
            user_id=current_user.id,
            email_domain=email[email.find('@'):] if '@' in email else None,
            new_auth_type=updated_user.auth_type,
            elapsed_ms=round(elapsed_time * 1000),
            unlink_time_ms=round(unlink_time * 1000)
        )
        
        return {
            "message": "Google account unlinked successfully",
            "email": updated_user.email,
            "auth_type": updated_user.auth_type
        }
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        elapsed_time = time.time() - start_time
        logger.warning(
            f"HTTP exception during account unlinking: {http_ex.detail}",
            event_type="account_unlinking_http_error",
            user_id=current_user.id,
            email_domain=email[email.find('@'):] if '@' in email else None,
            status_code=http_ex.status_code,
            detail=http_ex.detail,
            elapsed_ms=round(elapsed_time * 1000)
        )
        raise http_ex
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(
            "Error unlinking Google account",
            event_type="account_unlinking_error",
            user_id=current_user.id,
            email_domain=email[email.find('@'):] if '@' in email else None,
            error_type=type(e).__name__,
            error_details=str(e),
            elapsed_ms=round(elapsed_time * 1000)
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
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Google OAuth callback redirect.
    This endpoint receives the redirect from Google OAuth and redirects to the frontend
    with the authorization code or error.
    
    Args:
        code: Authorization code from Google
        error: Error from Google OAuth
        state: State parameter for CSRF protection
        db: Database session
        
    Returns:
        Redirect to frontend
    """
    import time
    start_time = time.time()
    
    from fastapi.responses import RedirectResponse
    from app.core.config import settings
    from fastapi import Request
    
    # Get request object for client info
    request = Request
    client_ip = getattr(request, "client", {}).get("host", "unknown")
    
    # Frontend URL to redirect to
    frontend_url = f"{settings.FRONTEND_URL}/api/auth/callback"
    
    logger.debug(
        "Received Google OAuth callback",
        event_type="google_oauth_callback_received",
        has_code=bool(code),
        has_error=bool(error),
        has_state=bool(state),
        client_ip=client_ip
    )
    
    # If there's an error, redirect to frontend with error
    if error:
        logger.error(
            "Error in Google OAuth flow",
            event_type="google_oauth_error",
            error=error,
            has_state=bool(state),
            client_ip=client_ip
        )
        redirect_url = f"{frontend_url}?error={error}"
        if state:
            redirect_url += f"&state={state}"
        return RedirectResponse(redirect_url)
    
    # If no code, redirect to frontend with error
    if not code:
        logger.error(
            "No code provided in Google OAuth callback",
            event_type="google_oauth_error",
            has_state=bool(state),
            client_ip=client_ip
        )
        redirect_url = f"{frontend_url}?error=no_code"
        if state:
            redirect_url += f"&state={state}"
        return RedirectResponse(redirect_url)
    
    # Redact code for logging
    redacted_code = code[:4] + "..." if len(code) > 4 else "***"
    
    elapsed_time = time.time() - start_time
    logger.info(
        "Redirecting to frontend with Google OAuth code",
        event_type="google_oauth_callback_redirect",
        code_length=len(code),
        has_state=bool(state),
        elapsed_ms=round(elapsed_time * 1000),
        client_ip=client_ip
    )
    
    # Redirect to frontend with code
    redirect_url = f"{frontend_url}?code={code}"
    if state:
        redirect_url += f"&state={state}"
    return RedirectResponse(redirect_url)

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
   import time
   start_time = time.time()
   
   # Redact code for logging
   redacted_code = callback.code[:4] + "..." if len(callback.code) > 4 else "***"
   
   logger.debug(
       "Received login with Google request",
       event_type="google_oauth_login_request",
       redirect_uri=callback.redirect_uri or "default",
       code_length=len(callback.code)
   )
   
   try:
       oauth_service = GoogleOAuthService(db)
       
       login_start = time.time()
       user, access_token = await oauth_service.login_with_google(callback.code, callback.redirect_uri)
       login_time = time.time() - login_start
       
       # Redact email for logging
       email = user.email
       redacted_email = email[:3] + "***" + email[email.find('@'):] if '@' in email and len(email) > 5 else "***"
       
       elapsed_time = time.time() - start_time
       logger.info(
           "Google OAuth login successful",
           event_type="google_oauth_login",
           user_id=user.id,
           email_domain=email[email.find('@'):] if '@' in email else None,
           auth_type=user.auth_type,
           is_new_user=user.created_at and (datetime.now(timezone.utc) - user.created_at < timedelta(minutes=1)),
           elapsed_ms=round(elapsed_time * 1000),
           login_time_ms=round(login_time * 1000)
       )
       
       # Log token details (without revealing the actual token)
       token_info = {
           "token_type": "bearer",
           "token_length": len(access_token) if access_token else 0
       }
       
       logger.debug(
           "Generated JWT token for Google OAuth login",
           event_type="google_oauth_token_generated",
           user_id=user.id,
           token_info=token_info
       )
       
       return Token(access_token=access_token, token_type="bearer")
   except HTTPException as http_ex:
       # Re-raise HTTP exceptions
       elapsed_time = time.time() - start_time
       logger.warning(
           f"HTTP exception during Google OAuth login: {http_ex.detail}",
           event_type="google_oauth_login_http_error",
           status_code=http_ex.status_code,
           detail=http_ex.detail,
           redirect_uri=callback.redirect_uri or "default",
           elapsed_ms=round(elapsed_time * 1000)
       )
       raise http_ex
   except Exception as e:
       elapsed_time = time.time() - start_time
       logger.error(
           "Google OAuth login error",
           event_type="google_oauth_login_error",
           error_type=type(e).__name__,
           error_details=str(e),
           redirect_uri=callback.redirect_uri or "default",
           code_prefix=redacted_code,
           elapsed_ms=round(elapsed_time * 1000)
       )
       raise HTTPException(
           status_code=status.HTTP_400_BAD_REQUEST,
           detail="Failed to authenticate with Google"
       )