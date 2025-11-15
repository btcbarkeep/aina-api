from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from database import get_session
from models import SignupRequest, UserBuildingAccess
from core.auth_helpers import (
    create_user_no_password,
    generate_password_setup_token,
)
from core.email_utils import send_password_setup_email

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(
    full_name: str,
    email: str,
    hoa_name: str,
    role: str = "hoa",
    session: Session = Depends(get_session),
):
    """
    Admin creates a user with NO password.
    User receives an email to set their password.
    """

    # 1. Create user record (no password yet)
    user = create_user_no_password(
        session=session,
        full_name=full_name,
        email=email,
        hoa_name=hoa_name,
    )

    # 2. Generate token for password setup
    token = generate_password_setup_token(email)

    # 3. Email the user
    send_password_setup_email(email, token)

    # 4. Assign initial role (HOA, manager, contractor)
    access = UserBuildingAccess(username=email, building_id=0, role=role)
    session.add(access)
    session.commit()

    return {
        "status": "success",
        "message": f"Account created for {email}. Password setup email sent.",
        "token": token,   # Useful for testing before email system goes live
    }
