# core/notifications.py
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from core.config import settings
from core.logging_config import logger

# -----------------------------------------------------
# 📨 Send webhook (Discord, Slack, etc.)
# -----------------------------------------------------
def send_webhook_message(message: str):
    webhook_url = settings.SYNC_WEBHOOK_URL
    if not webhook_url:
        logger.debug("Webhook URL not configured — skipping.")
        return

    try:
        payload = {"content": message}
        response = requests.post(webhook_url, json=payload)
        logger.info(f"Webhook sent (status {response.status_code})")
    except Exception as e:
        logger.warning(f"Webhook failed: {e}")


# -----------------------------------------------------
# 📧 Send email (SMTP)
# -----------------------------------------------------
def send_email(subject: str, body: str, to: str = None):
    smtp_host = settings.SMTP_HOST
    smtp_port = settings.SMTP_PORT
    smtp_user = settings.SMTP_USER
    smtp_pass = settings.SMTP_PASS

    # If a specific recipient isn't provided, fall back to default
    recipient = to or settings.SMTP_TO

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass, recipient]):
        logger.warning("Email credentials missing — skipping email.")
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        logger.info(f"Email sent to {recipient}")

    except Exception as e:
        logger.error(f"Email failed: {e}")
