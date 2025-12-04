# core/email_utils.py

from core.notifications import send_email
from core.logging_config import logger


def send_password_setup_email(email: str, token: str):
    """
    Sends the real password setup email using the main SMTP sender.
    """

    link = f"https://ainaprotocol.com/set-password?token={token}"

    subject = "Aina Protocol – Create Your Password"
    body = f"""
Aloha,

Your account has been created.

Click below to set your password:

{link}

Mahalo,
Aina Protocol Team
"""

    # Call the real SMTP email sender
    send_email(subject=subject, body=body, to=email)

    logger.info(f"Password setup email sent to {email}")

    return True
