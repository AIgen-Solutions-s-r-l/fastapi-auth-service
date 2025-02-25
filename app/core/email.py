"""Email service using SendGrid via Azure."""

import json
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.log.logging import logger


async def send_email(subject: str, recipients: List[str], body: str):
    """
    Send an email using SendGrid API.
    
    Args:
        subject: Email subject
        recipients: List of recipient email addresses
        body: Email body content (HTML)
        
    Raises:
        RuntimeError: If email settings are not configured or sending fails
    """
    if not settings.SENDGRID_API_KEY:
        raise RuntimeError("SendGrid API key not configured")
    
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
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code >= 400:
                logger.error(
                    f"Failed to send email: {response.status_code} - {response.text}",
                    event_type="email_send_error",
                    status_code=response.status_code,
                    response=response.text
                )
                raise RuntimeError(f"Failed to send email: {response.status_code} - {response.text}")
            
            logger.info(
                "Email sent successfully",
                event_type="email_sent",
                recipients=recipients,
                subject=subject
            )
            
            return response.status_code
            
    except Exception as e:
        logger.error(
            f"Error sending email: {str(e)}",
            event_type="email_send_exception",
            error=str(e)
        )
        raise RuntimeError(f"Error sending email: {str(e)}")