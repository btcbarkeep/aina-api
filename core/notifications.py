# core/notifications.py
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional
from io import BytesIO
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
def send_email(
    subject: str, 
    body: str, 
    to: str = None,
    recipients: Optional[List[str]] = None,
    attachments: Optional[List[dict]] = None,
    html_body: Optional[str] = None
):
    """
    Send email via SMTP.
    
    Args:
        subject: Email subject
        body: Plain text email body
        to: Single recipient email (deprecated, use recipients)
        recipients: List of recipient email addresses
        attachments: List of dicts with 'filename' and 'content' (bytes) or 'url' (presigned URL)
        html_body: Optional HTML email body
    """
    smtp_host = settings.SMTP_HOST
    smtp_port = settings.SMTP_PORT
    smtp_user = settings.SMTP_USER
    smtp_pass = settings.SMTP_PASS

    # Determine recipients
    if recipients:
        recipient_list = recipients
    elif to:
        recipient_list = [to]
    else:
        recipient_list = [settings.SMTP_TO] if settings.SMTP_TO else []

    if not recipient_list:
        logger.warning("No recipients specified — skipping email.")
        return

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        logger.warning("Email credentials missing — skipping email.")
        return

    try:
        msg = MIMEMultipart('alternative')
        msg["From"] = smtp_user
        msg["To"] = ", ".join(recipient_list)
        msg["Subject"] = subject
        
        # Add plain text body
        msg.attach(MIMEText(body, "plain"))
        
        # Add HTML body if provided
        if html_body:
            msg.attach(MIMEText(html_body, "html"))
        
        # Add attachments if provided
        if attachments:
            for attachment in attachments:
                if 'content' in attachment:
                    # Direct content attachment
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment['content'])
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {attachment["filename"]}'
                    )
                    msg.attach(part)
                elif 'url' in attachment:
                    # URL attachment - download and attach
                    try:
                        response = requests.get(attachment['url'], timeout=30)
                        response.raise_for_status()
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(response.content)
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename= {attachment["filename"]}'
                        )
                        msg.attach(part)
                    except Exception as e:
                        logger.warning(f"Failed to attach {attachment['filename']} from URL: {e}")

        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        logger.info(f"Email sent to {', '.join(recipient_list)}")

    except Exception as e:
        logger.error(f"Email failed: {e}")
        raise
