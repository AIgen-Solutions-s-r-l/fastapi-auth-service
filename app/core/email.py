from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.core.config import Settings
from pathlib import Path

# Create a Settings instance
settings = Settings()

# Configure email settings
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    TEMPLATE_FOLDER=Path(__file__).parent.parent / 'templates',
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

# Initialize FastMail
fastmail = FastMail(conf)

async def send_email(
    to_email: str,
    subject: str,
    template: str,
    context: dict
) -> None:
    """Send email using FastAPI-Mail."""
    message = MessageSchema(
        subject=subject,
        recipients=[to_email],
        template_body=context,
    )
    
    await fastmail.send_message(message, template_name=template) 