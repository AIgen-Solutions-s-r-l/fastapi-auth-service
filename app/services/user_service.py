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
            # Filter for potentially relevant subscriptions
            candidate_subscriptions = [
                sub for sub in user.subscriptions if sub.status in ["active", "trialing", "past_due", "canceled"]
            ]
            
            if candidate_subscriptions:
                # Define a priority for subscription statuses
                status_priority = {
                    "active": 1,
                    "trialing": 2,
                    "past_due": 3,
                    "canceled": 4
                }

                # Sort subscriptions:
                # 1. By status priority (ascending, so "active" comes first)
                # 2. By start_date (descending, so newest comes first for ties in priority)
                def sort_key(s: Subscription):
                    priority = status_priority.get(s.status, 5) # Default to lower priority for other statuses
                    # Ensure start_date is timezone-aware for comparison if it's None
                    start_date_ts = (s.start_date.timestamp() 
                                     if s.start_date 
                                     else datetime.min.replace(tzinfo=UTC).timestamp())
                    return (priority, -start_date_ts)

                candidate_subscriptions.sort(key=sort_key)
                active_subscription = candidate_subscriptions[0] # The first one is the most relevant

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
            await self.db.rollback()
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
        Send email to Zapier webhook.

        Args:
            email: Email to send
        """
        zapier_webhook_url = "https://hooks.zapier.com/hooks/catch/123456/abcdef" # Replace with actual URL
        payload = {"email": email}
        try:
            response = requests.post(zapier_webhook_url, json=payload, timeout=10)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            logger.info(f"Email {email} sent to Zapier successfully.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending email to Zapier: {e}")
            # Optionally, re-raise or handle more gracefully

    async def update_user_password(self, email: str, current_password: str, new_password: str) -> bool:
        """
        Update user's password.

        Args:
            email: Email of user to update
            current_password: Current password for verification
            new_password: New password

        Returns:
            bool: True if password was updated, False otherwise

        Raises:
            HTTPException: If authentication fails or new password is same as old
        """
        user = await self.authenticate_user(email, current_password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        if verify_password(new_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password cannot be the same as the old password"
            )

        user.hashed_password = get_password_hash(new_password)
        await self.db.commit()
        await self.db.refresh(user)
        return True

    async def send_password_change_confirmation(
        self, 
        user: User, 
        background_tasks: BackgroundTasks
    ) -> bool:
        """
        Send a password change confirmation email to a user.

        Args:
            user: The user to send the confirmation email to
            background_tasks: FastAPI BackgroundTasks for async email sending

        Returns:
            bool: True if email was sent successfully
        """
        try:
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
        user_id: int, 
        new_email: str, 
        current_email: str, 
        background_tasks: BackgroundTasks
    ) -> Tuple[bool, Optional[str]]:
        """
        Create an email change request and send verification email.

        Args:
            user_id: ID of the user requesting the change.
            new_email: The new email address.
            current_email: The current email address (for logging/verification).
            background_tasks: FastAPI BackgroundTasks for async email sending.

        Returns:
            Tuple[bool, Optional[str]]: Success status and the verification token if successful.
        
        Raises:
            HTTPException: If new email is already in use by another user.
        """
        # Check if the new email is already registered by another user
        existing_user_with_new_email = await self.get_user_by_email(new_email)
        if existing_user_with_new_email and existing_user_with_new_email.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New email address is already in use by another account."
            )

        try:
            # Generate a random token
            alphabet = string.ascii_letters + string.digits
            token = ''.join(secrets.choice(alphabet) for _ in range(64))
            
            # Set expiration time (e.g., 1 hour from now)
            expires_at = datetime.now(UTC) + timedelta(hours=1)
            
            # Create email change request record
            email_change_request = EmailChangeRequest(
                user_id=user_id,
                current_email=current_email,
                new_email=new_email,
                token=token,
                expires_at=expires_at,
                completed=False 
            )
            
            self.db.add(email_change_request)
            await self.db.commit()
            
            # Send verification email for the new email address
            email_service = EmailService(background_tasks, self.db)
            user = await self.get_user_by_id(user_id) # Fetch user to pass to email service
            if user: # Should always be true if user_id is valid
                 await email_service.send_email_change_verification(user, new_email, token)
            
            logger.info(
                f"Created email change request for user {user_id} to new email {new_email}",
                event_type="email_change_request_created",
                user_id=user_id,
                new_email=new_email
            )
            return True, token
            
        except IntegrityError: # Should be caught by the check above, but as a safeguard
            await self.db.rollback()
            logger.error(
                f"Integrity error creating email change request for user {user_id} to {new_email}.",
                event_type="email_change_request_integrity_error",
                user_id=user_id,
                new_email=new_email
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not process email change request due to a database conflict."
            )
        except Exception as e:
            await self.db.rollback()
            logger.error(
                f"Error creating email change request: {str(e)}",
                event_type="email_change_request_error",
                user_id=user_id,
                new_email=new_email,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating email change request: {str(e)}"
            )

    async def verify_email_change(self, token: str) -> Tuple[bool, str, Optional[User]]:
        """
        Verify an email change request using a token and update the user's email.

        Args:
            token: The verification token for email change.

        Returns:
            Tuple[bool, str, Optional[User]]: Success status, a message, and the updated user if successful.
        
        Raises:
            HTTPException: If token is invalid, expired, or other errors occur.
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
                    "Invalid email change token",
                    event_type="invalid_email_change_token",
                    token=token
                )
                return False, "Invalid or already used token.", None
                
            if datetime.now(UTC) > request_record.expires_at:
                logger.warning(
                    "Expired email change token",
                    event_type="expired_email_change_token",
                    token=token,
                    user_id=request_record.user_id
                )
                return False, "Email change token has expired.", None
                
            # Get the user
            user = await self.get_user_by_id(request_record.user_id)
            if not user: # Should not happen if request_record is valid
                logger.error(
                    "User not found for email change token",
                    event_type="user_not_found_for_email_change",
                    token=token,
                    user_id=request_record.user_id
                )
                return False, "User not found.", None

            # Check if the new email is already in use by ANOTHER user (race condition check)
            existing_user_with_new_email = await self.get_user_by_email(request_record.new_email)
            if existing_user_with_new_email and existing_user_with_new_email.id != user.id:
                logger.warning(
                    f"New email {request_record.new_email} for user {user.id} is now taken by user {existing_user_with_new_email.id}",
                    event_type="email_change_conflict_on_verify",
                    user_id=user.id,
                    new_email=request_record.new_email
                )
                # Mark the token as completed to prevent reuse, even though it failed
                request_record.completed = True
                await self.db.commit()
                return False, "The new email address has been taken by another account since the request was made.", None

            # Update user's email and mark as verified (since new email was verified)
            old_email = user.email
            user.email = request_record.new_email
            user.is_verified = True # New email is considered verified by this process
            
            # Mark request as completed
            request_record.completed = True
            
            await self.db.commit()
            await self.db.refresh(user)
            
            logger.info(
                f"Email changed for user {user.id} from {old_email} to {user.email}",
                event_type="email_changed_successfully",
                user_id=user.id,
                old_email=old_email,
                new_email=user.email
            )
            return True, "Email address successfully updated.", user
            
        except Exception as e:
            await self.db.rollback()
            logger.error(
                f"Error verifying email change: {str(e)}",
                event_type="email_change_verification_error",
                token=token,
                error=str(e)
            )
            # Do not raise HTTPException directly to allow specific messaging in the router
            return False, f"An unexpected error occurred: {str(e)}", None


# --- Password Reset Functions (outside UserService class as they might be called without user context) ---

async def create_password_reset_token(db: AsyncSession, email: str) -> str:
    """
    Create a token for password reset.

    Args:
        db: Async database session.
        email: Email of the user requesting reset.

    Returns:
        str: The password reset token.

    Raises:
        HTTPException: If user not found or other error.
    """
    user_service = UserService(db) # Instantiate UserService to use its methods
    user = await user_service.get_user_by_email(email)
    if not user:
        # Even if user not found, don't reveal this to prevent email enumeration.
        # Log it and return a dummy token or handle as per security policy.
        # For now, we'll proceed as if creating, but it won't be usable.
        # A better approach might be to always "succeed" from API perspective.
        logger.warning(f"Password reset requested for non-existent email: {email}", event_type="password_reset_nonexistent_email", email=email)
        # To avoid timing attacks, generate a token anyway but don't save it for non-existent user
        # However, for simplicity in this example, we'll raise if not found for now,
        # assuming the calling router handles the "user not found" case by still returning 200 OK.
        # This part needs careful security review in a real app.
        # Let's assume the router will handle the "not found" by not sending an email.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


    try:
        alphabet = string.ascii_letters + string.digits
        token = ''.join(secrets.choice(alphabet) for i in range(64))
        expires_at = datetime.now(UTC) + timedelta(hours=1) # Token valid for 1 hour

        # Invalidate previous tokens for this user
        await db.execute(
            update(User).where(User.id == user.id).values(
                password_reset_token=None, 
                password_reset_token_expires_at=None
            )
        )
        # It's better to store reset tokens in a separate table like EmailVerificationToken
        # For now, updating User model directly as per existing (simplified) structure
        user.password_reset_token = token
        user.password_reset_token_expires_at = expires_at
        
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"Password reset token created for user {user.id}", event_type="password_reset_token_created", user_id=user.id)
        return token
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating password reset token for {email}: {str(e)}", event_type="password_reset_token_error", email=email, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create password reset token.")

async def verify_reset_token(db: AsyncSession, token: str) -> int:
    """Verify password reset token and return user ID if valid."""
    result = await db.execute(
        select(User).where(User.password_reset_token == token)
    )
    user = result.scalar_one_or_none()

    if not user or user.password_reset_token_expires_at is None or datetime.now(UTC) > user.password_reset_token_expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    
    return user.id

async def reset_password(db: AsyncSession, user_id: int, new_password: str) -> bool:
    """Reset user's password."""
    user_service = UserService(db)
    user = await user_service.get_user_by_id(user_id)
    if not user: # Should not happen if verify_reset_token was called
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.hashed_password = get_password_hash(new_password)
    user.password_reset_token = None # Invalidate token
    user.password_reset_token_expires_at = None
    await db.commit()
    await db.refresh(user)
    logger.info(f"Password reset for user {user_id}", event_type="password_reset_success", user_id=user_id)
    return True
