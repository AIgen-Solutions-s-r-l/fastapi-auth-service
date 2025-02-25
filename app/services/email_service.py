"""Service layer for managing email communications."""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
import os

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email
from app.core.config import settings
from app.models.user import User
from app.log.logging import logger


class EmailService:
    """Service class for managing email communications."""

    def __init__(self, background_tasks: BackgroundTasks, db: AsyncSession):
        """
        Initialize with BackgroundTasks and database session.
        
        Args:
            background_tasks: FastAPI BackgroundTasks for async email sending
            db: Database session for accessing user data
        """
        self.background_tasks = background_tasks
        self.db = db
    
    async def _send_templated_email(
        self, 
        template_name: str,
        subject: str,
        recipients: List[str], 
        context: Dict[str, Any]
    ) -> None:
        """
        Send an email using a template.
        
        Args:
            template_name: Name of the template file (without .html extension)
            subject: Email subject line
            recipients: List of recipient email addresses
            context: Dictionary of template variables
            
        Raises:
            HTTPException: If email sending fails
        """
        try:
            # Get the template file path
            template_path = Path(__file__).parent.parent / "templates" / f"{template_name}.html"
            
            # Check if template exists
            if not template_path.exists():
                logger.error(f"Email template not found: {template_name}",
                           event_type="email_template_error",
                           template=template_name)
                raise HTTPException(
                    status_code=500,
                    detail=f"Email template {template_name} not found"
                )
            
            # Render the template
            with open(template_path, "r") as f:
                template_content = f.read()
            
            # Simple template rendering (In a real implementation, use Jinja2 properly)
            rendered_content = template_content
            for key, value in context.items():
                placeholder = "{{ " + key + " }}"
                rendered_content = rendered_content.replace(placeholder, str(value))
            
            # Send the email using SendGrid
            self.background_tasks.add_task(
                send_email,
                subject=subject,
                recipients=recipients,
                body=rendered_content
            )
            
            logger.info(
                f"Queued email: {template_name}",
                event_type="email_queued",
                template=template_name,
                recipients=recipients
            )
            
        except Exception as e:
            logger.error(
                f"Failed to send email: {str(e)}",
                event_type="email_error",
                template=template_name,
                recipients=recipients,
                error=str(e)
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send email: {str(e)}"
            )
    
    async def send_registration_confirmation(
        self, 
        user: User, 
        verification_token: str
    ) -> None:
        """
        Send registration confirmation email with verification link.
        
        Args:
            user: User model instance
            verification_token: Token for email verification
        """
        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
        
        await self._send_templated_email(
            template_name="registration_confirmation",
            subject="Confirm Your Registration",
            recipients=[str(user.email)],
            context={
                "username": user.username,
                "verification_link": verification_link,
                "hours_valid": 24  # Token validity in hours
            }
        )
    
    async def send_welcome_email(self, user: User) -> None:
        """
        Send welcome email after registration is confirmed.
        
        Args:
            user: User model instance
        """
        await self._send_templated_email(
            template_name="welcome",
            subject="Welcome to Our Service",
            recipients=[str(user.email)],
            context={
                "username": user.username,
                "login_link": f"{settings.FRONTEND_URL}/login"
            }
        )
    
    async def send_payment_confirmation(
        self, 
        user: User, 
        plan_name: str, 
        amount: float, 
        credit_amount: float,
        renewal_date: datetime
    ) -> None:
        """
        Send payment confirmation with plan purchase details and renewal date.
        
        Args:
            user: User model instance
            plan_name: Name of the purchased plan
            amount: Amount paid
            credit_amount: Amount of credits received
            renewal_date: Date when the plan will renew
        """
        await self._send_templated_email(
            template_name="payment_confirmation",
            subject="Payment Confirmation",
            recipients=[str(user.email)],
            context={
                "username": user.username,
                "plan_name": plan_name,
                "amount": amount,
                "credit_amount": credit_amount,
                "purchase_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "renewal_date": renewal_date.strftime("%Y-%m-%d %H:%M"),
                "dashboard_link": f"{settings.FRONTEND_URL}/dashboard"
            }
        )
    
    async def send_password_change_request(
        self, 
        user: User, 
        reset_token: str
    ) -> None:
        """
        Send password change request verification email.
        
        Args:
            user: User model instance
            reset_token: Token for password reset
        """
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        
        await self._send_templated_email(
            template_name="password_change_request",
            subject="Password Change Request",
            recipients=[str(user.email)],
            context={
                "username": user.username,
                "reset_link": reset_link,
                "hours_valid": 24  # Token validity in hours
            }
        )
    
    async def send_password_change_confirmation(self, user: User) -> None:
        """
        Send confirmation after password has been changed.
        
        Args:
            user: User model instance
        """
        await self._send_templated_email(
            template_name="password_change_confirmation",
            subject="Password Change Confirmation",
            recipients=[str(user.email)],
            context={
                "username": user.username,
                "login_link": f"{settings.FRONTEND_URL}/login",
                "ip_address": "Not available",  # Could be passed in from the request
                "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            }
        )
    
    async def send_one_time_credit_purchase(
        self, 
        user: User, 
        amount: float, 
        credits: float
    ) -> None:
        """
        Send confirmation for one-time credit purchase.
        
        Args:
            user: User model instance
            amount: Amount paid
            credits: Amount of credits purchased
        """
        await self._send_templated_email(
            template_name="one_time_credit_purchase",
            subject="Credit Purchase Confirmation",
            recipients=[str(user.email)],
            context={
                "username": user.username,
                "amount": amount,
                "credits": credits,
                "purchase_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "dashboard_link": f"{settings.FRONTEND_URL}/dashboard"
            }
        )
    
    async def send_plan_upgrade(
        self, 
        user: User, 
        old_plan_name: str, 
        new_plan_name: str,
        additional_credits: float,
        new_renewal_date: datetime
    ) -> None:
        """
        Send notification of plan upgrade.
        
        Args:
            user: User model instance
            old_plan_name: Name of the previous plan
            new_plan_name: Name of the upgraded plan
            additional_credits: Additional credits received from upgrade
            new_renewal_date: New renewal date after upgrade
        """
        await self._send_templated_email(
            template_name="plan_upgrade",
            subject="Plan Upgrade Confirmation",
            recipients=[str(user.email)],
            context={
                "username": user.username,
                "old_plan": old_plan_name,
                "new_plan": new_plan_name,
                "additional_credits": additional_credits,
                "upgrade_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "renewal_date": new_renewal_date.strftime("%Y-%m-%d %H:%M"),
                "dashboard_link": f"{settings.FRONTEND_URL}/dashboard"
            }
        )