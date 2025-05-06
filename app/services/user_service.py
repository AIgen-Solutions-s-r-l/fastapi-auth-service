"""Service layer for user-related operations."""

from datetime import datetime, UTC, timedelta
from typing import Optional, Dict, Any, Tuple
import secrets
import string
import asyncio

from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload # Added for eager loading
from sqlalchemy.exc import IntegrityError
import requests
import stripe # Added for Stripe direct calls if needed

from app.core.security import get_password_hash, verify_password
from app.models.user import User, EmailVerificationToken, EmailChangeRequest
from app.models.credit import UserCredit # Added
from app.models.plan import Subscription, Plan # Added
from app.schemas.auth_schemas import UserStatusResponse, SubscriptionStatusResponse # Added
from app.services.email_service import EmailService
from app.services.stripe_service import StripeService # Added
from app.log.logging import logger
from app.core.config import settings # Added for Stripe API key


class UserService:
    """Service class for user operations."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db
        self.stripe_service = StripeService(db_session=self.db) # Pass db session

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Get user by ID.
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
            .options(
                selectinload(User.credits), # Eager load credits
                selectinload(User.subscriptions).selectinload(Subscription.plan) # Eager load subscriptions and their plans
            )
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
            .options(
                selectinload(User.credits),
                selectinload(User.subscriptions).selectinload(Subscription.plan)
            )
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        email: str,
        password: str,
        is_admin: bool = False,
        auto_verify: bool = False
    ) -> User:
        """
        Create a new user.

        Args:
            email: Email for new user
            password: Plain text password
            is_admin: Whether user is admin
            auto_verify: Whether to auto-verify the email

        Returns:
            User: Created user

        Raises:
            HTTPException: If email already exists
        """
        try:
            user = User(
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
                detail="Email already registered"
            )

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate a user using email.

        Args:
            email: Email to authenticate
            password: Plain text password to verify

        Returns:
            Optional[User]: Authenticated user if successful, None otherwise
        """
        user = await self.get_user_by_email(email)
        if not user:
            return None
        # Ensure hashed_password is not None before verifying (for OAuth-only users)
        if user.hashed_password and not verify_password(password, user.hashed_password):
            return None
        if not user.hashed_password and user.auth_type == "google": # OAuth only user trying password login
             return None
        return user
    
    async def get_user_status_details(self, user_id: int) -> Optional[UserStatusResponse]:
        """
        Retrieves detailed status for a given user, including account status,
        credit balance, and active subscription details.

        Args:
            user_id: The ID of the user.

        Returns:
            Optional[UserStatusResponse]: Detailed user status or None if user not found.
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            return None

        credits_remaining = 0
        if user.credits:
            credits_remaining = int(user.credits.balance) if user.credits.balance is not None else 0
        
        subscription_response: Optional[SubscriptionStatusResponse] = None
        # Find the most recent active or trialing subscription
        active_subscription: Optional[Subscription] = None
        if user.subscriptions:
            # Filter for active or trialing subscriptions and sort by creation date descending
            relevant_subscriptions = [
                sub for sub in user.subscriptions if sub.status in ["active", "trialing"] and sub.is_active
            ]
            if relevant_subscriptions:
                active_subscription = max(relevant_subscriptions, key=lambda s: s.start_date or datetime.min.replace(tzinfo=UTC))


        if active_subscription and active_subscription.plan:
            plan_name = active_subscription.plan.name
            stripe_sub_id_db = active_subscription.stripe_subscription_id
            
            # Default values, to be updated from Stripe if possible
            trial_end_date_stripe: Optional[datetime] = None
            current_period_end_stripe: Optional[datetime] = None
            cancel_at_period_end_stripe: bool = False
            stripe_subscription_status = active_subscription.status # Fallback to DB status

            if stripe_sub_id_db:
                try:
                    # Ensure Stripe API key is set for this specific call
                    # This is a bit redundant if StripeService init already does it,
                    # but good for direct stripe calls.
                    if not stripe.api_key:
                        stripe.api_key = settings.STRIPE_SECRET_KEY
                        stripe.api_version = settings.STRIPE_API_VERSION

                    stripe_sub = await asyncio.to_thread(
                        stripe.Subscription.retrieve,
                        stripe_sub_id_db
                    )
                    if stripe_sub:
                        stripe_subscription_status = stripe_sub["status"]
                        if stripe_sub.get("trial_end"):
                            trial_end_date_stripe = datetime.fromtimestamp(stripe_sub["trial_end"], UTC)
                        if stripe_sub.get("current_period_end"):
                            current_period_end_stripe = datetime.fromtimestamp(stripe_sub["current_period_end"], UTC)
                        cancel_at_period_end_stripe = stripe_sub["cancel_at_period_end"]
                        
                        # Update local subscription status if different from Stripe
                        if active_subscription.status != stripe_subscription_status:
                            logger.info(
                                f"Updating local subscription {active_subscription.id} status from '{active_subscription.status}' to '{stripe_subscription_status}' based on Stripe.",
                                event_type="subscription_status_sync",
                                user_id=user_id,
                                db_subscription_id=active_subscription.id,
                                stripe_subscription_id=stripe_sub_id_db
                            )
                            active_subscription.status = stripe_subscription_status
                            # Potentially update is_active based on Stripe status
                            if stripe_subscription_status not in ["active", "trialing", "past_due"]: # incomplete, unpaid, canceled
                                active_subscription.is_active = False
                            await self.db.commit()
                            await self.db.refresh(active_subscription)


                except stripe.error.StripeError as e:
                    logger.error(
                        f"Stripe API error retrieving subscription {stripe_sub_id_db} for user {user_id}: {str(e)}",
                        event_type="stripe_api_error",
                        user_id=user_id,
                        stripe_subscription_id=stripe_sub_id_db,
                        error_message=str(e)
                    )
                except Exception as e:
                    logger.error(
                        f"Unexpected error retrieving subscription {stripe_sub_id_db} for user {user_id}: {str(e)}",
                        event_type="stripe_unexpected_error",
                        user_id=user_id,
                        stripe_subscription_id=stripe_sub_id_db,
                        error_message=str(e)
                    )
            
            subscription_response = SubscriptionStatusResponse(
                stripe_subscription_id=stripe_sub_id_db or "N/A",
                status=stripe_subscription_status, # Use status from Stripe if available
                plan_name=plan_name,
                trial_end_date=trial_end_date_stripe,
                current_period_end=current_period_end_stripe,
                cancel_at_period_end=cancel_at_period_end_stripe
            )

        return UserStatusResponse(
            user_id=str(user.id), # Assuming user.id is int, convert to str if schema expects UUID as str
            account_status=user.account_status,
            credits_remaining=credits_remaining,
            subscription=subscription_response
        )

    async def update_user_email(self, email: str, current_password: str, new_email: str) -> User:
        """
        Update user's email address.

        Args:
            email: Current email of user to update
            current_password: Current password for verification
            new_email: New email address

        Returns:
            User: Updated user object

        Raises:
            HTTPException: If authentication fails or email is already in use
        """
        user = await self.authenticate_user(email, current_password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
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

    async def delete_user(self, email: str, password: str) -> bool:
        """
        Delete a user.

        Args:
            email: Email of user to delete
            password: Password for verification

        Returns:
            bool: True if user was deleted, False otherwise

        Raises:
            HTTPException: If user not found or password incorrect
        """
        user = await self.authenticate_user(email, password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
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
                email=user.email
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
        
    async def send_email_to_zapier(self, email: str) -> None:
        """
        Sends the registered user's email to the Zapier webhook.
        """
        webhook_url = 'https://hooks.zapier.com/hooks/catch/15113518/2cn7t0k/'
        data = {'email': email}
        try:
            response = requests.post(webhook_url, json=data)
            if response.status_code == 200:
                logger.info("Successfully sent email to Zapier", email=email)
            else:
                logger.error("Failed to send email to Zapier",
                            email=email,
                            status_code=response.status_code,
                            response_text=response.text)
        except Exception as e:
            logger.error("Exception when sending email to Zapier", error=str(e), email=email)

    async def update_user_password(self, email: str, current_password: str, new_password: str) -> bool:
        """
        Update user password.

        Args:
            email: Email of user to update
            current_password: Current password for verification
            new_password: New password

        Returns:
            bool: True if password was updated successfully

        Raises:
            HTTPException: If authentication fails
        """
        user = await self.authenticate_user(email, current_password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        user.hashed_password = get_password_hash(new_password)
        await self.db.commit()
        
        logger.info(
            f"Password changed for user {user.id}",
            event_type="password_changed",
            user_id=user.id,
            email=user.email
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

    async def create_email_change_request(
        self,
        user: User,
        new_email: str,
        password: str
    ) -> Tuple[bool, str, Optional[EmailChangeRequest]]:
        """
        Create a request to change a user's email address.
        
        Args:
            user: User requesting the change
            new_email: New email address
            password: Current password for verification
            
        Returns:
            Tuple containing:
            - success status (bool)
            - message (str)
            - email change request if successful (Optional[EmailChangeRequest])
        """
        # Verify password
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            logger.warning(
                "Invalid password for email change request",
                event_type="email_change_request_error",
                user_id=user.id,
                email=user.email,
                error_type="invalid_password"
            )
            return False, "Invalid password", None
            
        # Check if new email is already in use
        existing_user = await self.get_user_by_email(new_email)
        if existing_user and existing_user.id != user.id:
            logger.warning(
                "Email already registered",
                event_type="email_change_request_error",
                user_id=user.id,
                email=user.email,
                new_email=new_email,
                error_type="email_in_use"
            )
            return False, "New email address is already in use.", None
            
        try:
            # Generate a random token
            alphabet = string.ascii_letters + string.digits
            token = ''.join(secrets.choice(alphabet) for _ in range(64))
            
            # Set expiration time (e.g., 1 hour from now)
            expires_at = datetime.now(UTC) + timedelta(hours=1)
            
            # Create email change request record
            email_change_request = EmailChangeRequest(
                user_id=user.id,
                current_email=user.email,
                new_email=new_email,
                token=token,
                expires_at=expires_at,
                completed=False
            )
            
            self.db.add(email_change_request)
            await self.db.commit()
            await self.db.refresh(email_change_request)
            
            logger.info(
                f"Created email change request for user {user.id}",
                event_type="email_change_request_created",
                user_id=user.id,
                current_email=user.email,
                new_email=new_email
            )
            
            return True, "Email change request created. Please check your new email for verification.", email_change_request
            
        except Exception as e:
            await self.db.rollback()
            logger.error(
                f"Error creating email change request: {str(e)}",
                event_type="email_change_request_error",
                user_id=user.id,
                email=user.email,
                new_email=new_email,
                error=str(e)
            )
            return False, f"Error creating email change request: {str(e)}", None

    async def verify_email_change(self, token: str) -> Tuple[bool, str, Optional[User]]:
        """
        Verify an email change request using a token.
        
        Args:
            token: The verification token
            
        Returns:
            Tuple containing:
            - success status (bool)
            - message (str)
            - updated user object if successful (Optional[User])
        """
        try:
            # Find the email change request
            result = await self.db.execute(
                select(EmailChangeRequest).where(
                    EmailChangeRequest.token == token,
                    EmailChangeRequest.completed == False # noqa: E712
                )
            )
            request_record = result.scalar_one_or_none()
            
            if not request_record:
                logger.warning(
                    "Invalid or completed email change token",
                    event_type="email_change_verification_error",
                    token=token,
                    error_type="invalid_token"
                )
                return False, "Invalid or completed email change token.", None
                
            # Check if token is expired
            if datetime.now(UTC) > request_record.expires_at:
                logger.warning(
                    "Expired email change token",
                    event_type="email_change_verification_error",
                    token=token,
                    user_id=request_record.user_id,
                    error_type="expired_token"
                )
                return False, "Email change token has expired.", None
                
            # Get the user
            user = await self.get_user_by_id(request_record.user_id) # Use existing method
            
            if not user:
                logger.error(
                    "User not found for email change token",
                    event_type="email_change_verification_error",
                    token=token,
                    user_id=request_record.user_id,
                    error_type="user_not_found"
                )
                return False, "User not found.", None
                
            # Update user's email and mark as unverified
            user.email = request_record.new_email
            user.is_verified = False # User needs to verify the new email
            
            # Mark request as completed
            request_record.completed = True
            
            await self.db.commit()
            await self.db.refresh(user)
            
            logger.info(
                f"Email changed successfully for user {user.id}",
                event_type="email_changed",
                user_id=user.id,
                old_email=request_record.current_email,
                new_email=user.email
            )
            
            return True, "Email changed successfully. Please verify your new email address.", user
            
        except IntegrityError: # Catch if the new email is somehow taken despite earlier checks
            await self.db.rollback()
            logger.error(
                "New email address is already in use during final update.",
                event_type="email_change_verification_error",
                token=token,
                user_id=request_record.user_id if 'request_record' in locals() else 'unknown',
                new_email=request_record.new_email if 'request_record' in locals() else 'unknown',
                error_type="email_in_use_race_condition"
            )
            return False, "New email address is already in use.", None
        except Exception as e:
            await self.db.rollback()
            logger.error(
                f"Error verifying email change: {str(e)}",
                event_type="email_change_verification_error",
                token=token,
                error=str(e)
            )
            return False, f"Error verifying email change: {str(e)}", None


# Standalone functions for easier use in routers if needed, wrapping UserService methods

async def create_user(db: AsyncSession, email: str, password: str, is_admin: bool = False) -> User:
    return await UserService(db).create_user(email, password, is_admin)

async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    return await UserService(db).authenticate_user(email, password)

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    return await UserService(db).get_user_by_email(email)

async def delete_user(db: AsyncSession, email: str, password: str) -> bool:
    return await UserService(db).delete_user(email, password)

async def update_user_password(db: AsyncSession, email: str, current_password: str, new_password: str) -> bool:
    return await UserService(db).update_user_password(email, current_password, new_password)

async def create_password_reset_token(db: AsyncSession, email: str) -> str:
    """
    Create a password reset token for a user.
    
    Args:
        db: Database session
        email: Email of the user
        
    Returns:
        str: The password reset token
        
    Raises:
        HTTPException: If user not found or error creating token
    """
    user_service = UserService(db)
    user = await user_service.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # Generate a random token
        alphabet = string.ascii_letters + string.digits
        token = ''.join(secrets.choice(alphabet) for i in range(64))
        
        # Set expiration time (e.g., 1 hour from now)
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        
        # Create token record (assuming PasswordResetToken model exists)
        from app.models.user import PasswordResetToken  # Local import
        reset_token = PasswordResetToken(
            token=token,
            user_id=user.id,
            expires_at=expires_at,
            used=False
        )
        
        db.add(reset_token)
        await db.commit()
        
        logger.info(
            f"Created password reset token for user {user.id}",
            event_type="password_reset_token_created",
            user_id=user.id,
            email=user.email
        )
        
        return token
        
    except Exception as e:
        await db.rollback()
        logger.error(
            f"Error creating password reset token: {str(e)}",
            event_type="password_reset_token_error",
            user_id=user.id,
            email=user.email,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Error creating password reset token: {str(e)}")

async def verify_reset_token(db: AsyncSession, token: str) -> int:
    """Verify password reset token and return user ID."""
    from app.models.user import PasswordResetToken  # Local import
    
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == token,
            PasswordResetToken.used == False, # noqa
            PasswordResetToken.expires_at > datetime.now(UTC)
        )
    )
    token_record = result.scalar_one_or_none()
    
    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
        
    return token_record.user_id

async def reset_password(db: AsyncSession, user_id: int, new_password: str) -> bool:
    """Reset user password."""
    from app.models.user import PasswordResetToken # Local import
    user_service = UserService(db)
    user = await user_service.get_user_by_id(user_id) # Use existing method
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = get_password_hash(new_password)
    
    # Mark token as used (assuming token is passed or handled elsewhere)
    # This part might need adjustment based on how token is managed in the flow
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used == False) # noqa
        .values(used=True)
    )
    
    await db.commit()
    logger.info(f"Password reset for user {user_id}", event_type="password_reset", user_id=user_id)
    return True
