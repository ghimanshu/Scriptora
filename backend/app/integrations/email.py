import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


def send_email(recipient, subject, body):
    cfg = get_settings()
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = cfg.mail_from, recipient, subject
    message.set_content(body)
    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
        if cfg.smtp_use_tls:
            smtp.starttls()
        if cfg.smtp_username:
            smtp.login(cfg.smtp_username, cfg.smtp_password)
        smtp.send_message(message)
