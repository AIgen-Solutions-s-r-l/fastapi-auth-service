# Email Sending Implementation Plan

## Overview

This document outlines the specific implementation steps to diagnose and fix the email sending issue in the auth_service. The issue is that users are not receiving registration confirmation emails when registering with an email address.

## Implementation Steps

### 1. Create Email Diagnostic Endpoint

First, we'll create a diagnostic endpoint to test email sending directly:

```python
# Add to app/routers/auth_router.py

@router.post(
    "/test-email",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Test email sent successfully"},
        500: {"description": "Failed to send test email"}
    }
)
async def test_email(
    email_test: Dict[str, str],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Test endpoint to verify email sending functionality.
    Requires an email address to send the test to.
    """
    try:
        email = email_test.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address is required"
            )
            
        # Create email service
        email_service = EmailService(background_tasks, db)
        
        # Send a test email directly (not in background)
        result = await send_email(
            subject="Test Email from Auth Service",
            recipients=[email],
            body="<p>This is a test email to verify the email sending functionality.</p>"
        )
        
        logger.info(
            "Test email sent",
            event_type="test_email_sent",
            recipient=email,
            status_code=result
        )
        
        return {
            "message": "Test email sent",
            "status_code": result,
            "recipient": email
        }
    except Exception as e:
        logger.error(
            "Failed to send test email",
            event_type="test_email_error",
            error=str(e),
            error_type=type(e).__name__
        )
        
        return {
            "message": "Failed to send test email",
            "error": str(e),
            "error_type": type(e).__name__
        }
```

### 2. Enhance Email Sending Function

Next, we'll enhance the email sending function with better error handling and logging:

```python
# Modify app/core/email.py

import json
import httpx
import asyncio
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.log.logging import logger


async def send_email(subject: str, recipients: List[str], body: str):
    """
    Send an email using SendGrid API with enhanced logging.
    
    Args:
        subject: Email subject
        recipients: List of recipient email addresses
        body: Email body content (HTML)
        
    Raises:
        RuntimeError: If email settings are not configured or sending fails
    """
    if not settings.SENDGRID_API_KEY:
        logger.error("SendGrid API key not configured", event_type="email_config_error")
        raise RuntimeError("SendGrid API key not configured")
    
    # Log the attempt to send email
    logger.info(
        "Attempting to send email",
        event_type="email_send_attempt",
        recipients=recipients,
        subject=subject
    )
    
    # Prepare SendGrid API request
    url = f"{settings.SENDGRID_HOST}/v3/mail/send"
    
    # Format recipients as SendGrid expects
    formatted_recipients = [{"email": recipient} for recipient in recipients]
    
    # Prepare the email payload
    payload = {
        "personalizations": [
            {
                "to": formatted_recipients,
                "subject": subject
            }
        ],
        "from": {
            "email": settings.EMAIL_FROM_ADDRESS,
            "name": settings.EMAIL_FROM_NAME
        },
        "content": [
            {
                "type": "text/html",
                "value": body
            }
        ]
    }
    
    # Add Azure domain tracking settings if configured
    if settings.AZURE_DOMAIN:
        payload["tracking_settings"] = {
            "click_tracking": {
                "enable": True,
                "enable_text": True
            },
            "open_tracking": {
                "enable": True
            }
        }
        
        # Add custom domain for click and open tracking
        payload["mail_settings"] = {
            "sandbox_mode": {
                "enable": False
            }
        }
    
    headers = {
        "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        # Log the request details (excluding sensitive info)
        logger.debug(
            "SendGrid API request prepared",
            event_type="email_request_prepared",
            url=url,
            recipients=recipients,
            subject=subject
        )
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            # Log the raw response for debugging
            logger.debug(
                "SendGrid API response received",
                event_type="email_api_response",
                status_code=response.status_code,
                response_text=response.text,
                response_headers=dict(response.headers)
            )
            
            if response.status_code >= 400:
                error_message = f"Failed to send email: {response.status_code} - {response.text}"
                logger.error(
                    error_message,
                    event_type="email_send_error",
                    status_code=response.status_code,
                    response=response.text
                )
                raise RuntimeError(error_message)
            
            logger.info(
                "Email sent successfully",
                event_type="email_sent",
                recipients=recipients,
                subject=subject,
                status_code=response.status_code
            )
            
            return response.status_code
            
    except httpx.RequestError as e:
        # Network-related errors
        error_message = f"Network error when sending email: {str(e)}"
        logger.error(
            error_message,
            event_type="email_network_error",
            error=str(e),
            error_type=type(e).__name__
        )
        raise RuntimeError(error_message)
    except Exception as e:
        error_message = f"Error sending email: {str(e)}"
        logger.error(
            error_message,
            event_type="email_send_exception",
            error=str(e),
            error_type=type(e).__name__
        )
        raise RuntimeError(error_message)


async def send_email_with_retry(subject: str, recipients: List[str], body: str, max_retries: int = 3):
    """
    Send an email with retry logic for transient failures.
    
    Args:
        subject: Email subject
        recipients: List of recipient email addresses
        body: Email body content (HTML)
        max_retries: Maximum number of retry attempts
        
    Returns:
        int: HTTP status code from the API response
        
    Raises:
        RuntimeError: If all retry attempts fail
    """
    retry_count = 0
    last_exception = None
    
    while retry_count < max_retries:
        try:
            return await send_email(subject, recipients, body)
        except Exception as e:
            last_exception = e
            retry_count += 1
            
            # Only retry for certain types of errors (network errors, 5xx responses)
            if isinstance(e, httpx.RequestError) or "500" in str(e) or "503" in str(e):
                # Exponential backoff: 1s, 2s, 4s, etc.
                wait_time = 2 ** (retry_count - 1)
                
                logger.warning(
                    f"Email sending failed, retrying in {wait_time}s (attempt {retry_count}/{max_retries})",
                    event_type="email_retry",
                    retry_count=retry_count,
                    max_retries=max_retries,
                    wait_time=wait_time,
                    error=str(e)
                )
                
                await asyncio.sleep(wait_time)
            else:
                # Don't retry for client errors or other issues
                logger.error(
                    f"Email sending failed with non-retriable error",
                    event_type="email_error_non_retriable",
                    error=str(e)
                )
                raise e
    
    # If we've exhausted all retries
    logger.error(
        f"Email sending failed after {max_retries} retries",
        event_type="email_all_retries_failed",
        error=str(last_exception)
    )
    raise last_exception
```

### 3. Update EmailService to Use Retry Logic

Now we'll update the EmailService to use our new retry logic:

```python
# Modify app/services/email_service.py

# Import the new send_email_with_retry function
from app.core.email import send_email, send_email_with_retry

# Then modify the _send_templated_email method:

async def _send_templated_email(
    self, 
    template_name: str,
    subject: str,
    recipients: List[str], 
    context: Dict[str, Any]
) -> None:
    """
    Send an email using a template with retry logic.
    
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
        
        # Send the email using SendGrid with retry logic
        self.background_tasks.add_task(
            send_email_with_retry,  # Use the retry version
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
```

### 4. Add Template Verification Function

Let's add a function to verify that templates can be properly rendered:

```python
# Add to app/services/email_service.py

def verify_template(template_name: str, context: Dict[str, Any]) -> bool:
    """
    Verify that a template exists and can be rendered with the given context.
    
    Args:
        template_name: Name of the template file (without .html extension)
        context: Dictionary of template variables
        
    Returns:
        bool: True if template exists and can be rendered, False otherwise
    """
    try:
        template_path = Path(__file__).parent.parent / "templates" / f"{template_name}.html"
        
        if not template_path.exists():
            logger.error(
                f"Template verification failed: {template_name} not found",
                event_type="template_verification_error",
                template=template_name,
                error="template_not_found"
            )
            return False
        
        with open(template_path, "r") as f:
            template_content = f.read()
        
        # Check if all context keys are in the template
        for key in context.keys():
            placeholder = "{{ " + key + " }}"
            if placeholder not in template_content:
                logger.warning(
                    f"Template variable {key} not found in template {template_name}",
                    event_type="template_variable_missing",
                    template=template_name,
                    variable=key
                )
        
        # Try rendering the template
        rendered_content = template_content
        for key, value in context.items():
            placeholder = "{{ " + key + " }}"
            rendered_content = rendered_content.replace(placeholder, str(value))
        
        return True
    except Exception as e:
        logger.error(
            f"Template verification failed: {str(e)}",
            event_type="template_verification_error",
            template=template_name,
            error=str(e)
        )
        return False
```

### 5. Add Template Verification Endpoint

Let's add an endpoint to verify all email templates:

```python
# Add to app/routers/auth_router.py

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
            "username": "test_user",
            "verification_link": "https://example.com/verify?token=test_token",
            "hours_valid": 24
        }
    )
    
    # Test welcome template
    results["welcome"] = email_service.verify_template(
        "welcome",
        {
            "username": "test_user",
            "login_link": "https://example.com/login"
        }
    )
    
    # Test password change request template
    results["password_change_request"] = email_service.verify_template(
        "password_change_request",
        {
            "username": "test_user",
            "reset_link": "https://example.com/reset?token=test_token",
            "hours_valid": 24
        }
    )
    
    # Test password change confirmation template
    results["password_change_confirmation"] = email_service.verify_template(
        "password_change_confirmation",
        {
            "username": "test_user",
            "login_link": "https://example.com/login",
            "ip_address": "127.0.0.1",
            "time": "2025-02-26 11:30:00 UTC"
        }
    )
    
    # Add other templates as needed
    
    return {
        "message": "Template verification completed",
        "results": results
    }
```

### 6. Update Configuration Validation

Let's add validation for email configuration:

```python
# Add to app/core/config.py

def validate_email_config():
    """
    Validate email configuration and log warnings for missing or invalid settings.
    
    Returns:
        bool: True if configuration is valid, False otherwise
    """
    valid = True
    
    if not settings.SENDGRID_API_KEY:
        logger.error(
            "SendGrid API key not configured",
            event_type="config_error",
            setting="SENDGRID_API_KEY"
        )
        valid = False
    
    if not settings.EMAIL_FROM_ADDRESS:
        logger.error(
            "Email FROM address not configured",
            event_type="config_error",
            setting="EMAIL_FROM_ADDRESS"
        )
        valid = False
    
    if not settings.EMAIL_FROM_NAME:
        logger.warning(
            "Email FROM name not configured",
            event_type="config_warning",
            setting="EMAIL_FROM_NAME"
        )
    
    if not settings.FRONTEND_URL:
        logger.warning(
            "Frontend URL not configured",
            event_type="config_warning",
            setting="FRONTEND_URL"
        )
    
    return valid

# Then call this at startup in app/main.py
from app.core.config import validate_email_config

@app.on_event("startup")
async def startup_event():
    # Validate email configuration
    email_config_valid = validate_email_config()
    if not email_config_valid:
        logger.warning(
            "Email configuration is invalid or incomplete",
            event_type="startup_warning",
            component="email"
        )
```

## Testing Plan

1. **Test Email Configuration**
   - Run the application and check logs for any configuration warnings
   - Verify that all required environment variables are set

2. **Test Template Verification**
   - Call the `/verify-email-templates` endpoint
   - Verify that all templates exist and can be rendered

3. **Test Email Sending**
   - Call the `/test-email` endpoint with your email address
   - Check if the email is received
   - Verify logs for any errors

4. **Test Registration Flow**
   - Register a new user
   - Check logs for email sending attempts
   - Verify if the verification email is received

## Deployment Steps

1. Update the code with the changes outlined above
2. Verify SendGrid API key and domain configuration
3. Deploy the updated code
4. Monitor logs for any email-related errors
5. Test the complete registration flow

## Fallback Options

If SendGrid continues to have issues:

1. **Alternative Email Provider**
   - Consider implementing an alternative email provider (e.g., Mailgun, AWS SES)
   - Create an email provider interface to easily switch between providers

2. **SMTP Fallback**
   - Implement a direct SMTP fallback option
   - Configure with a reliable SMTP provider

3. **Disable Email Verification**
   - As a last resort, consider making email verification optional
   - Auto-verify users but still send welcome emails