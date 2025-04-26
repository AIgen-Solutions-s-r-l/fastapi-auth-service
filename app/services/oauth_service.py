"""Service for OAuth authentication."""

from typing import Dict, Any, Optional, Tuple
import httpx
import random
from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, timedelta

from app.core.config import settings
from app.models.user import User
from app.services.user_service import UserService
from app.core.security import create_access_token
from app.log.logging import logger


class GoogleOAuthService:
    """Service for Google OAuth authentication."""
    
    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db
        self.user_service = UserService(db)
        
    async def get_authorization_url(self, redirect_uri: Optional[str] = None) -> str:
        """
        Get Google authorization URL.
        
        Args:
            redirect_uri: Optional custom redirect URI
            
        Returns:
            str: Authorization URL for Google OAuth
        """
        import time
        start_time = time.time()
        
        logger.debug(
            "Generating Google authorization URL",
            event_type="google_auth_url_start",
            redirect_uri=redirect_uri or "default"
        )
        
        oauth_redirect = redirect_uri or settings.GOOGLE_REDIRECT_URI
        
        # Build authorization URL
        params = {
            'client_id': settings.GOOGLE_CLIENT_ID,
            'redirect_uri': oauth_redirect,
            'scope': settings.OAUTH_SCOPES,
            'response_type': 'code',
            'access_type': 'offline',
            'prompt': 'consent',
            'state': self._generate_state_param()  # Add state parameter for CSRF protection
        }
        
        # Construct URL with parameters
        base_url = "https://accounts.google.com/o/oauth2/auth"
        
        # Properly URL encode the parameters
        from urllib.parse import urlencode
        query_string = urlencode(params)
        
        auth_url = f"{base_url}?{query_string}"
        
        elapsed_time = time.time() - start_time
        logger.debug(
            "Generated Google authorization URL",
            event_type="google_auth_url_complete",
            redirect_uri=oauth_redirect,
            scopes=settings.OAUTH_SCOPES,
            elapsed_ms=round(elapsed_time * 1000),
            has_state=bool(params.get('state'))
        )
        
        return auth_url
    
    def _generate_state_param(self) -> str:
        """
        Generate a random state parameter for CSRF protection.
        
        Returns:
            str: Random state parameter
        """
        import string
        import random
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(32))
    
    async def exchange_code_for_tokens(self, code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.
        
        Args:
            code: Authorization code from Google
            redirect_uri: Optional custom redirect URI
            
        Returns:
            Dict[str, Any]: Tokens response from Google
            
        Raises:
            HTTPException: If token exchange fails
        """
        import time
        start_time = time.time()
        
        # Redact code for logging (show first 4 chars only)
        redacted_code = code[:4] + "..." if len(code) > 4 else "***"
        
        logger.debug(
            "Starting token exchange with Google",
            event_type="oauth_token_exchange_start",
            redirect_uri=redirect_uri or "default",
            code_length=len(code)
        )
        
        oauth_redirect = redirect_uri or settings.GOOGLE_REDIRECT_URI
        
        # Prepare token request
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'code': code,
            'redirect_uri': oauth_redirect,
            'grant_type': 'authorization_code'
        }
        
        # Make token request
        try:
            request_start = time.time()
            async with httpx.AsyncClient() as client:
                # Using url keyword for better test mocking compatibility
                response = await client.post(url=token_url, data=data)
            
            request_time = time.time() - request_start
            
            # Check for errors
            if response.status_code != 200:
                logger.error(
                    "Failed to exchange code for tokens",
                    event_type="oauth_token_exchange_error",
                    status_code=response.status_code,
                    response=response.text,
                    redirect_uri=oauth_redirect,
                    request_time_ms=round(request_time * 1000),
                    code_prefix=redacted_code
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to authenticate with Google"
                )
                
            # Return tokens
            tokens = response.json()
            
            # Log success with redacted token info
            token_info = {
                "has_access_token": "access_token" in tokens,
                "has_refresh_token": "refresh_token" in tokens,
                "has_id_token": "id_token" in tokens,
                "token_type": tokens.get("token_type"),
                "expires_in": tokens.get("expires_in")
            }
            
            elapsed_time = time.time() - start_time
            logger.info(
                "Successfully exchanged code for tokens",
                event_type="oauth_token_exchange_success",
                token_info=token_info,
                elapsed_ms=round(elapsed_time * 1000),
                request_time_ms=round(request_time * 1000)
            )
            
            return tokens
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(
                "Exception during code exchange",
                event_type="oauth_token_exchange_exception",
                error=str(e),
                error_type=type(e).__name__,
                elapsed_ms=round(elapsed_time * 1000),
                code_prefix=redacted_code
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to authenticate with Google"
            )
    
    async def get_user_profile(self, access_token: str) -> Dict[str, Any]:
        """
        Get user profile from Google using access token.
        
        Args:
            access_token: Access token from Google
            
        Returns:
            Dict[str, Any]: User profile from Google
            
        Raises:
            HTTPException: If profile retrieval fails
        """
        import time
        start_time = time.time()
        
        # Redact token for logging
        redacted_token = access_token[:5] + "..." if len(access_token) > 5 else "***"
        
        logger.debug(
            "Fetching user profile from Google",
            event_type="oauth_userinfo_start",
            token_prefix=redacted_token[:5]
        )
        
        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            # Make userinfo request
            request_start = time.time()
            async with httpx.AsyncClient() as client:
                # Using url keyword for better test mocking compatibility
                response = await client.get(url=userinfo_url, headers=headers)
            
            request_time = time.time() - request_start
            
            # Check for errors
            if response.status_code != 200:
                logger.error(
                    "Failed to get user profile",
                    event_type="oauth_userinfo_error",
                    status_code=response.status_code,
                    response=response.text,
                    request_time_ms=round(request_time * 1000)
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user information from Google"
                )
                
            # Return user profile
            profile = response.json()
            
            # Log success with redacted profile info
            profile_info = {
                "has_sub": "sub" in profile,
                "has_email": "email" in profile,
                "has_name": "name" in profile,
                "has_picture": "picture" in profile,
                "email_verified": profile.get("email_verified", False)
            }
            
            elapsed_time = time.time() - start_time
            logger.info(
                "Successfully retrieved user profile",
                event_type="oauth_userinfo_success",
                profile_info=profile_info,
                elapsed_ms=round(elapsed_time * 1000),
                request_time_ms=round(request_time * 1000)
            )
            
            return profile
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(
                "Exception during profile retrieval",
                event_type="oauth_userinfo_exception",
                error=str(e),
                error_type=type(e).__name__,
                elapsed_ms=round(elapsed_time * 1000)
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user information from Google"
            )
    
    async def find_or_create_user(self, profile: Dict[str, Any]) -> User:
        """
        Find existing user or create a new one from Google profile.
        
        Args:
            profile: Google user profile
            
        Returns:
            User: Existing or newly created user
        """
        import time
        start_time = time.time()
        
        # Redact email for logging
        email = profile.get('email', '')
        redacted_email = email[:3] + "***" + email[email.find('@'):] if '@' in email and len(email) > 5 else "***"
        google_id = profile.get('sub', '')
        redacted_google_id = google_id[:5] + "***" if len(google_id) > 5 else "***"
        
        logger.debug(
            "Finding or creating user from Google profile",
            event_type="oauth_find_or_create_user_start",
            email_domain=email[email.find('@'):] if '@' in email else None,
            has_google_id=bool(google_id),
            has_email=bool(email)
        )
        
        # Try to find user by Google ID
        query_start = time.time()
        result = await self.db.execute(
            select(User).where(User.google_id == profile.get('sub'))
        )
        user = result.scalar_one_or_none()
        query_time = time.time() - query_start
        
        if user:
            # Found existing user with this Google ID
            elapsed_time = time.time() - start_time
            logger.info(
                "Found existing user by Google ID",
                event_type="oauth_user_found_by_google_id",
                user_id=user.id,
                email_domain=email[email.find('@'):] if '@' in email else None,
                elapsed_ms=round(elapsed_time * 1000),
                query_time_ms=round(query_time * 1000)
            )
            return user
            
        # Try to find user by email
        query_start = time.time()
        result = await self.db.execute(
            select(User).where(User.email == profile.get('email'))
        )
        user = result.scalar_one_or_none()
        query_time = time.time() - query_start
        
        if user:
            # Found user with same email - update with Google ID
            logger.info(
                "Found existing user by email, updating with Google ID",
                event_type="oauth_user_found_by_email",
                user_id=user.id,
                email_domain=email[email.find('@'):] if '@' in email else None,
                previous_auth_type=user.auth_type,
                was_verified=user.is_verified,
                query_time_ms=round(query_time * 1000)
            )
            
            user.google_id = profile.get('sub')
            user.auth_type = 'both' if user.hashed_password else 'google'
            
            # If email wasn't verified before, verify it now (Google verifies emails)
            if not user.is_verified:
                user.is_verified = True
                logger.info(
                    "Marking user as verified through Google OAuth",
                    event_type="oauth_user_verified",
                    user_id=user.id,
                    email_domain=email[email.find('@'):] if '@' in email else None
                )
                
            update_start = time.time()
            await self.db.commit()
            await self.db.refresh(user)
            update_time = time.time() - update_start
            
            elapsed_time = time.time() - start_time
            logger.info(
                "Updated existing user with Google ID",
                event_type="oauth_user_updated",
                user_id=user.id,
                new_auth_type=user.auth_type,
                elapsed_ms=round(elapsed_time * 1000),
                update_time_ms=round(update_time * 1000)
            )
            return user
            
        # Create new user from Google profile
        logger.info(
            "Creating new user from Google profile",
            event_type="oauth_user_creation_start",
            email_domain=email[email.find('@'):] if '@' in email else None
        )
        
        new_user = User(
            email=profile.get('email'),
            google_id=profile.get('sub'),
            auth_type='google',
            is_verified=True,  # Google already verified the email
            hashed_password=None  # No password for OAuth users
        )
        
        create_start = time.time()
        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)
        create_time = time.time() - create_start
        
        elapsed_time = time.time() - start_time
        logger.info(
            "Created new user from Google OAuth",
            event_type="oauth_user_created",
            user_id=new_user.id,
            email_domain=email[email.find('@'):] if '@' in email else None,
            auth_type=new_user.auth_type,
            elapsed_ms=round(elapsed_time * 1000),
            create_time_ms=round(create_time * 1000)
        )
        
        return new_user
    
    async def link_google_account(self, user: User, profile: Dict[str, Any]) -> User:
        """
        Link Google account to existing user.
        
        Args:
            user: Existing user
            profile: Google user profile
            
        Returns:
            User: Updated user with linked Google account
        """
        user.google_id = profile.get('sub')
        user.auth_type = 'both'
        
        # If email wasn't verified before, verify it now (Google verifies emails)
        if not user.is_verified:
            user.is_verified = True
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info(
            "Linked Google account to existing user",
            event_type="oauth_account_linked",
            user_id=user.id,
            email=user.email,
            google_id=profile.get('sub')
        )
        
        return user
        
    async def unlink_google_account(self, user: User) -> User:
        """
        Unlink Google account from user.
        
        Args:
            user: User to unlink Google account from
            
        Returns:
            User: Updated user with unlinked Google account
            
        Raises:
            HTTPException: If user has no password
        """
        # Ensure user has a password before unlinking
        if not user.hashed_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot unlink Google account without setting a password first"
            )
            
        user.google_id = None
        user.auth_type = 'password'
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info(
            "Unlinked Google account from user",
            event_type="oauth_account_unlinked",
            user_id=user.id,
            email=user.email
        )
        
        return user

    async def login_with_google(self, code: str, redirect_uri: Optional[str] = None) -> Tuple[User, str]:
        """
        Complete Google OAuth login flow and generate JWT token.
        
        Args:
            code: Authorization code from Google
            redirect_uri: Optional custom redirect URI
            
        Returns:
            Tuple[User, str]: User object and JWT access token
            
        Raises:
            HTTPException: If any part of the flow fails
        """
        import time
        overall_start_time = time.time()
        
        # Redact code for logging
        redacted_code = code[:4] + "..." if len(code) > 4 else "***"
        
        logger.debug(
            "Starting Google OAuth login flow",
            event_type="oauth_login_flow_start",
            redirect_uri=redirect_uri or "default",
            code_length=len(code)
        )
        
        # Exchange code for tokens
        token_exchange_start = time.time()
        tokens = await self.exchange_code_for_tokens(code, redirect_uri)
        token_exchange_time = time.time() - token_exchange_start
        
        # Get user profile
        profile_start = time.time()
        profile = await self.get_user_profile(tokens['access_token'])
        profile_time = time.time() - profile_start
        
        # Find or create user
        user_start = time.time()
        user = await self.find_or_create_user(profile)
        user_time = time.time() - user_start
        
        # Generate JWT token (same as regular login)
        token_start = time.time()
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
        expire_time = datetime.now(timezone.utc) + expires_delta

        # log all timings
        logger.info(
            "Google OAuth login flow timings: {token_exchange_time_ms}ms, {profile_time_ms}ms, {user_time_ms}ms, {token_time_ms}ms / {expire_time} / {expires_delta}",
            token_exchange_time_ms=round(token_exchange_time * 1000),
            profile_time_ms=round(profile_time * 1000),
            user_time_ms=round(user_time * 1000),
            token_time_ms=round(token_start * 1000),
            expire_time=expire_time.isoformat(),
            expires_delta=expires_delta.total_seconds()
        )
        
        # Use email as the subject for new tokens (same as existing system)
        access_token = create_access_token(
            data={
                "sub": user.email,
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        token_time = time.time() - token_start
        
        # Redact email for logging
        email = user.email
        redacted_email = email[:3] + "***" + email[email.find('@'):] if '@' in email and len(email) > 5 else "***"
        
        overall_time = time.time() - overall_start_time
        logger.info(
            "Google OAuth login successful",
            event_type="oauth_login_success",
            user_id=user.id,
            email_domain=email[email.find('@'):] if '@' in email else None,
            auth_type=user.auth_type,
            is_new_user=user.created_at and (datetime.now(timezone.utc) - user.created_at < timedelta(minutes=1)),
            overall_time_ms=round(overall_time * 1000),
            token_exchange_time_ms=round(token_exchange_time * 1000),
            profile_time_ms=round(profile_time * 1000),
            user_time_ms=round(user_time * 1000),
            token_time_ms=round(token_time * 1000)
        )
        
        return user, access_token