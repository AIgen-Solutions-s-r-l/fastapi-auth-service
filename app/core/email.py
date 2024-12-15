from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.core.config import Settings
from pathlib import Path

conf = ConnectionConfig(
    MAIL_USERNAME=Settings.MAIL_USERNAME,
    MAIL_PASSWORD=Settings.MAIL_PASSWORD,
    MAIL_FROM=Settings.MAIL_FROM,
    MAIL_PORT=Settings.MAIL_PORT,
    MAIL_SERVER=Settings.MAIL_SERVER,
    MAIL_SSL_TLS=Settings.MAIL_SSL_TLS,
    MAIL_STARTTLS=Settings.MAIL_STARTTLS,
    TEMPLATE_FOLDER=Path(__file__).parent.parent / 'templates'
)

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
    
    fm = FastMail(conf)
    await fm.send_message(message, template_name=template) 