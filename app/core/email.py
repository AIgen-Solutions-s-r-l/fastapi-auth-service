from typing import Optional
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.core.config import settings

# Initialize FastMail as None by default
fastmail: Optional[FastMail] = None

# Only configure email if all required settings are present
if all([
    settings.MAIL_USERNAME,
    settings.MAIL_PASSWORD,
    settings.MAIL_FROM,
    settings.MAIL_SERVER
]):
    conf = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
        MAIL_STARTTLS=settings.MAIL_STARTTLS,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True
    )
    fastmail = FastMail(conf)

async def send_email(subject: str, recipients: list[str], body: str):
    """
    Send an email using FastMail.
    
    Args:
        subject: Email subject
        recipients: List of recipient email addresses
        body: Email body content
        
    Raises:
        RuntimeError: If email settings are not configured
    """
    if not fastmail:
        raise RuntimeError("Email settings not configured")
        
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=body,
        subtype="html"
    )
    
    await fastmail.send_message(message) 