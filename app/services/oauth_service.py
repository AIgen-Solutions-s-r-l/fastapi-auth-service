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
        oauth_redirect = redirect_uri or settings.GOOGLE_REDIRECT_URI
        
        # Build authorization URL
        params = {
            'client_id': settings.GOOGLE_CLIENT_ID,
            'redirect_uri': oauth_redirect,
            'scope': settings.OAUTH_SCOPES,
            'response_type': 'code',
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        # Construct URL with parameters
        base_url = "https://accounts.google.com/o/oauth2/auth"
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        
        return f"{base_url}?{query_string}"
    
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
            async with httpx.AsyncClient() as client:
                # Using url keyword for better test mocking compatibility
                response = await client.post(url=token_url, data=data)
                
            # Check for errors
            if response.status_code != 200:
                logger.error(
                    "Failed to exchange code for tokens",
                    event_type="oauth_token_exchange_error",
                    status_code=response.status_code,
                    response=response.text
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to authenticate with Google"
                )
                
            # Return tokens
            tokens = response.json()
            return tokens
        except Exception as e:
            logger.error(
                "Exception during code exchange",
                event_type="oauth_token_exchange_exception",
                error=str(e),
                error_type=type(e).__name__
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
        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            # Make userinfo request
            async with httpx.AsyncClient() as client:
                # Using url keyword for better test mocking compatibility
                response = await client.get(url=userinfo_url, headers=headers)
                
            # Check for errors
            if response.status_code != 200:
                logger.error(
                    "Failed to get user profile",
                    event_type="oauth_userinfo_error",
                    status_code=response.status_code,
                    response=response.text
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user information from Google"
                )
                
            # Return user profile
            profile = response.json()
            return profile
        except Exception as e:
            logger.error(
                "Exception during profile retrieval",
                event_type="oauth_userinfo_exception",
                error=str(e),
                error_type=type(e).__name__
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
        # Try to find user by Google ID
        result = await self.db.execute(
            select(User).where(User.google_id == profile.get('sub'))
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Found existing user with this Google ID
            return user
            
        # Try to find user by email
        result = await self.db.execute(
            select(User).where(User.email == profile.get('email'))
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Found user with same email - update with Google ID
            user.google_id = profile.get('sub')
            user.auth_type = 'both' if user.hashed_password else 'google'
            
            # If email wasn't verified before, verify it now (Google verifies emails)
            if not user.is_verified:
                user.is_verified = True
                
            await self.db.commit()
            await self.db.refresh(user)
            return user
            
        # Create new user from Google profile
        new_user = User(
            email=profile.get('email'),
            google_id=profile.get('sub'),
            auth_type='google',
            is_verified=True,  # Google already verified the email
            hashed_password=None  # No password for OAuth users
        )
        
        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)
        
        logger.info(
            "Created new user from Google OAuth",
            event_type="oauth_user_created",
            email=profile.get('email')
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
        # Exchange code for tokens
        tokens = await self.exchange_code_for_tokens(code, redirect_uri)
        
        # Get user profile
        profile = await self.get_user_profile(tokens['access_token'])
        
        # Find or create user
        user = await self.find_or_create_user(profile)
        
        # Generate JWT token (same as regular login)
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
        expire_time = datetime.now(timezone.utc) + expires_delta
        
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
        
        logger.info(
            "Google OAuth login successful",
            event_type="oauth_login_success",
            user_id=user.id,
            email=user.email
        )
        
        return user, access_token