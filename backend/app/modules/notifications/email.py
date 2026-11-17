from email.message import EmailMessage
import smtplib
import ssl
from app.core.config import settings


def send_email(recipient: str, subject: str, body: str, html_body: str | None = None) -> None:
    if not settings.smtp_enabled:
        raise RuntimeError("SMTP is disabled")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
