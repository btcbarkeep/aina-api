def send_password_setup_email(email: str, token: str):
    """
    Email sending stub.
    Replace with SendGrid / SES soon.
    """
    link = f"https://ainaprotocol.com/set-password?token={token}"

    print("\n📧 EMAIL SENT (stub)")
    print(f"To: {email}")
    print(f"Password Setup Link: {link}\n")

    return True
