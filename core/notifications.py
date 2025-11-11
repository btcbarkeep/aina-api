# core/notifications.py
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from core.config import settings

# -----------------------------------------------------
# 📨 Send webhook (Discord, Slack, etc.)
# -----------------------------------------------------
def send_webhook_message(message: str):
    webhook_url = settings.SYNC_WEBHOOK_URL
    if not webhook_url:
        print("[NOTIFY] Webhook URL not configured — skipping.")
        return

    try:
        payload = {"content": message}
        response = requests.post(webhook_url, json=payload)
        print(f"[NOTIFY] Webhook sent (status {response.status_code})")
    except Exception as e:
        print(f"[NOTIFY] Webhook failed: {e}")


# -----------------------------------------------------
# 📧 Send email (SMTP)
# -----------------------------------------------------
def send_email(subject: str, body: str):
    smtp_host = settings.SMTP_HOST
    smtp_port = settings.SMTP_PORT
    smtp_user = settings.SMTP_USER
    smtp_pass = settings.SMTP_PASS
    recipient = settings.SMTP_TO

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass, recipient]):
        print("[NOTIFY] Email credentials missing — skipping email.")
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
        print(f"[NOTIFY] Email sent to {recipient}")

    except Exception as e:
        print(f"[NOTIFY] Email failed: {e}")
