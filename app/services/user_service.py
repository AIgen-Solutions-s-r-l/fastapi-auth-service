"""Service layer for user-related operations."""

from datetime import datetime, UTC, timedelta
from typing import Optional, Dict, Any, Tuple
import secrets
import string

from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.security import get_password_hash, verify_password
from app.models.user import User, EmailVerificationToken
from app.services.email_service import EmailService
from app.log.logging import logger


class UserService:
    """Service class for user operations."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.

        Args:
            username: Username to look up

        Returns:
            Optional[User]: User if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.

        Args:
            email: Email to look up

        Returns:
            Optional[User]: User if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        is_admin: bool = False,
        auto_verify: bool = False
    ) -> User:
        """
        Create a new user.

        Args:
            username: Username for new user
            email: Email for new user
            password: Plain text password
            is_admin: Whether user is admin
            auto_verify: Whether to auto-verify the email

        Returns:
            User: Created user

        Raises:
            HTTPException: If username/email already exists
        """
        try:
            user = User(
                username=username,
                email=email,
                hashed_password=get_password_hash(password),
                is_admin=is_admin,
                is_verified=auto_verify
            )
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            return user
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already registered"
            )

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate a user.

        Args:
            username: Username to authenticate
            password: Plain text password to verify

        Returns:
            Optional[User]: Authenticated user if successful, None otherwise
        """
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def update_user_email(self, username: str, current_password: str, new_email: str) -> User:
        """
        Update user's email address.

        Args:
            username: Username of user to update
            current_password: Current password for verification
            new_email: New email address

        Returns:
            User: Updated user object

        Raises:
            HTTPException: If authentication fails or email is already in use
        """
        user = await self.authenticate_user(username, current_password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        # Check if new email is already in use
        existing_user = await self.get_user_by_email(new_email)
        if existing_user and existing_user.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        try:
            # Update email and set verification status to false
            user.email = new_email
            user.is_verified = False
            await self.db.commit()
            await self.db.refresh(user)
            return user
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

    async def delete_user(self, username: str, password: str) -> bool:
        """
        Delete a user.

        Args:
            username: Username of user to delete
            password: Password for verification

        Returns:
            bool: True if user was deleted, False otherwise

        Raises:
            HTTPException: If user not found or password incorrect
        """
        user = await self.authenticate_user(username, password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        try:
            await self.db.delete(user)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error deleting user: {str(e)}"
            )

    async def create_verification_token(self, user_id: int) -> str:
        """
        Create a token for email verification.

        Args:
            user_id: ID of the user to verify

        Returns:
            str: The verification token

        Raises:
            HTTPException: If the user is not found
        """
        try:
            # Get the user
            result = await self.db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            # Generate a random token
            alphabet = string.ascii_letters + string.digits
            token = ''.join(secrets.choice(alphabet) for _ in range(64))
            
            # Set expiration time (24 hours from now)
            expires_at = datetime.now(UTC) + timedelta(hours=24)
            
            # Create token record
            verification_token = EmailVerificationToken(
                token=token,
                user_id=user_id,
                expires_at=expires_at,
                used=False
            )
            
            # Remove any existing unused tokens for this user
            # Use SQLAlchemy's text() function for raw SQL
            sql = text("DELETE FROM email_verification_tokens WHERE user_id = :user_id AND used = FALSE")
            await self.db.execute(sql, {"user_id": user_id})
            
            # Save the new token
            self.db.add(verification_token)
            await self.db.commit()
            
            logger.info(
                f"Created verification token for user {user_id}",
                event_type="verification_token_created",
                user_id=user_id
            )
            
            return token
            
        except Exception as e:
            await self.db.rollback()
            logger.error(
                f"Error creating verification token: {str(e)}",
                event_type="verification_token_error",
                user_id=user_id,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating verification token: {str(e)}"
            )

    async def verify_email(self, token: str) -> Tuple[bool, Optional[User]]:
        """
        Verify a user's email using a verification token.

        Args:
            token: The verification token

        Returns:
            Tuple[bool, Optional[User]]: Success status and the verified user if successful

        Raises:
            HTTPException: If the token is invalid or expired
        """
        try:
            # Find the token
            result = await self.db.execute(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.token == token,
                    EmailVerificationToken.used == False  # noqa: E712
                )
            )
            token_record = result.scalar_one_or_none()
            
            if not token_record:
                logger.warning(
                    "Invalid verification token",
                    event_type="invalid_verification_token",
                    token=token
                )
                return False, None
                
            # Check if token is expired
            if datetime.now(UTC) > token_record.expires_at:
                logger.warning(
                    "Expired verification token",
                    event_type="expired_verification_token",
                    token=token,
                    user_id=token_record.user_id
                )
                return False, None
                
            # Get the user
            result = await self.db.execute(
                select(User).where(User.id == token_record.user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(
                    "User not found for verification token",
                    event_type="user_not_found_for_token",
                    token=token,
                    user_id=token_record.user_id
                )
                return False, None
                
            # Update user verification status
            user.is_verified = True
            
            # Mark token as used
            token_record.used = True
            
            await self.db.commit()
            await self.db.refresh(user)
            
            logger.info(
                f"Email verified for user {user.id}",
                event_type="email_verified",
                user_id=user.id,
                username=user.username
            )
            
            return True, user
            
        except Exception as e:
            await self.db.rollback()
            logger.error(
                f"Error verifying email: {str(e)}",
                event_type="email_verification_error",
                token=token,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error verifying email: {str(e)}"
            )

    async def send_verification_email(
        self, 
        user: User, 
        background_tasks: BackgroundTasks
    ) -> bool:
        """
        Send a verification email to a user.

        Args:
            user: The user to send verification email to
            background_tasks: FastAPI BackgroundTasks for async email sending

        Returns:
            bool: True if email was sent successfully
        """
        try:
            # Create verification token
            token = await self.create_verification_token(user.id)
            
            # Create email service and send email
            email_service = EmailService(background_tasks, self.db)
            await email_service.send_registration_confirmation(user, token)
            
            logger.info(
                f"Sent verification email to user {user.id}",
                event_type="verification_email_sent",
                user_id=user.id,
                email=str(user.email)
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Error sending verification email: {str(e)}",
                event_type="verification_email_error",
                user_id=user.id,
                email=str(user.email),
                error=str(e)
            )
            return False

    async def update_user_password(self, username: str, current_password: str, new_password: str) -> bool:
        """
        Update user password.

        Args:
            username: Username of user to update
            current_password: Current password for verification
            new_password: New password

        Returns:
            bool: True if password was updated successfully

        Raises:
            HTTPException: If authentication fails
        """
        user = await self.authenticate_user(username, current_password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        user.hashed_password = get_password_hash(new_password)
        await self.db.commit()
        
        logger.info(
            f"Password changed for user {user.id}",
            event_type="password_changed",
            user_id=user.id,
            username=user.username
        )
        
        return True

    async def send_password_change_confirmation(
        self, 
        user: User, 
        background_tasks: BackgroundTasks
    ) -> bool:
        """
        Send a password change confirmation email.

        Args:
            user: The user who changed their password
            background_tasks: FastAPI BackgroundTasks for async email sending

        Returns:
            bool: True if email was sent successfully
        """
        try:
            # Create email service and send email
            email_service = EmailService(background_tasks, self.db)
            await email_service.send_password_change_confirmation(user)
            
            logger.info(
                f"Sent password change confirmation to user {user.id}",
                event_type="password_change_confirmation_sent",
                user_id=user.id,
                email=str(user.email)
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Error sending password change confirmation: {str(e)}",
                event_type="password_change_confirmation_error",
                user_id=user.id,
                email=str(user.email),
                error=str(e)
            )
            return False


# Function exports for backward compatibility
async def create_user(db: AsyncSession, username: str, email: str, password: str, is_admin: bool = False) -> User:
    """Create a new user."""
    service = UserService(db)
    return await service.create_user(username, email, password, is_admin)

async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[User]:
    """Authenticate a user."""
    service = UserService(db)
    return await service.authenticate_user(username, password)

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """Get user by username."""
    service = UserService(db)
    return await service.get_user_by_username(username)

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get user by email."""
    service = UserService(db)
    return await service.get_user_by_email(email)

async def delete_user(db: AsyncSession, username: str, password: str) -> bool:
    """Delete a user."""
    service = UserService(db)
    return await service.delete_user(username, password)

async def update_user_password(db: AsyncSession, username: str, current_password: str, new_password: str) -> bool:
    """Update user password."""
    service = UserService(db)
    return await service.update_user_password(username, current_password, new_password)

async def create_password_reset_token(db: AsyncSession, email: str) -> str:
    """Create a password reset token."""
    service = UserService(db)
    user = await service.get_user_by_email(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    # TODO: Implement token creation
    return "dummy_token"

async def verify_reset_token(token: str) -> int:
    """Verify a password reset token."""
    # TODO: Implement token verification
    return 1

async def reset_password(db: AsyncSession, user_id: int, new_password: str) -> bool:
    """Reset user password."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    user.hashed_password = get_password_hash(new_password)
    await db.commit()
    return True
