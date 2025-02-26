"""Email service using SendGrid via Azure."""

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
        
    Returns:
        int: HTTP status code from the API response
        
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