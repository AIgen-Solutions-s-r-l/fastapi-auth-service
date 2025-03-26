"""Router module for authentication utility endpoints."""

from typing import Dict, Any

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.email_service import EmailService
from app.log.logging import logger

router = APIRouter()

@router.get(
    "/verify-email-templates",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Template verification results"}
    }
)
async def verify_email_templates(
    db: AsyncSession = Depends(get_db)
):
    """
    Verify that all email templates exist and can be rendered.
    """
    results = {}
    
    # Create email service
    email_service = EmailService(BackgroundTasks(), db)
    
    # Test registration confirmation template
    results["registration_confirmation"] = email_service.verify_template(
        "registration_confirmation",
        {
            "verification_link": "https://example.com/verify?token=test_token",
            "hours_valid": 24
        }
    )
    
    # Test welcome template
    results["welcome"] = email_service.verify_template(
        "welcome",
        {
            "login_link": "https://example.com/login"
        }
    )
    
    # Test password change request template
    results["password_change_request"] = email_service.verify_template(
        "password_change_request",
        {
            "reset_link": "https://example.com/reset?token=test_token",
            "hours_valid": 24
        }
    )
    
    # Test password change confirmation template
    results["password_change_confirmation"] = email_service.verify_template(
        "password_change_confirmation",
        {
            "login_link": "https://example.com/login",
            "ip_address": "127.0.0.1",
            "time": "2025-02-26 11:30:00 UTC"
        }
    )
    
    # Test email change verification template
    results["email_change_verification"] = email_service.verify_template(
        "email_change_verification",
        {
            "email": "new.email@example.com",
            "verification_link": "https://example.com/verify-email-change?token=test_token",
            "hours_valid": 24
        }
    )
    
    # Test email change confirmation template
    results["email_change_confirmation"] = email_service.verify_template(
        "email_change_confirmation",
        {
            "email": "new.email@example.com",
            "login_link": "https://example.com/login",
            "ip_address": "127.0.0.1",
            "time": "2025-02-26 11:30:00 UTC"
        }
    )
    
    # Test one time credit purchase template
    results["one_time_credit_purchase"] = email_service.verify_template(
        "one_time_credit_purchase",
        {
            "amount": 50.0,
            "credits": 100.0,
            "purchase_date": "2025-02-26 11:30:00",
            "dashboard_link": "https://example.com/dashboard"
        }
    )
    
    # Test plan upgrade template
    results["plan_upgrade"] = email_service.verify_template(
        "plan_upgrade",
        {
            "old_plan": "Basic",
            "new_plan": "Premium",
            "additional_credits": 200.0,
            "upgrade_date": "2025-02-26 11:30:00",
            "renewal_date": "2025-03-26 11:30:00",
            "dashboard_link": "https://example.com/dashboard"
        }
    )
    
    return {
        "message": "Template verification completed",
        "results": results
    }