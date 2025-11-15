# routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlmodel import Session

from database import get_session
from models import SignupRequest, UserBuildingAccess
from core.auth_helpers import (
    create_user_no_password,
    generate_password_setup_token,
)
from core.email_utils import send_password_setup_email

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------
# Request schema for admin-created accounts
# ---------------------------------------------------------
class AdminCreateAccountRequest(BaseModel):
    full_name: str
    email: EmailStr
    organization_name
    role: str = "hoa"         # "hoa", "manager", "contractor"
    building_id: int | None = None  # optional; can be assigned later


# ---------------------------------------------------------
# Admin: Create user + send password setup email
# ---------------------------------------------------------
@router.post(
    "/create-account",
    summary="Admin: Create a user account and email password setup link",
)
def admin_create_account(
    payload: AdminCreateAccountRequest,
    session: Session = Depends(get_session),
):
    """
    Admin creates a user with NO password.

    Flow:
    1. Create user record without a password.
    2. Generate a one-time password setup token.
    3. Email the user a link to set their password.
    4. (Optional) Attach initial building + role.
    """

    # 1. Create user (will raise 400 if email already exists)
    try:
        user = create_user_no_password(
            session=session,
            full_name=payload.full_name,
            email=payload.email,
            hoa_name=payload.hoa_name,
        )
    except HTTPException:
        # just bubble up the HTTPException from helper
        raise

    # 2. Generate token for password setup
    token = generate_password_setup_token(user.email)

    # 3. Email the user
    #    send_password_setup_email should build the full link from the token
    send_password_setup_email(user.email, token)

    # 4. Optionally assign initial role + building
    if payload.building_id is not None:
        access = UserBuildingAccess(
            username=user.username,
            building_id=payload.building_id,
            role=payload.role,
        )
        session.add(access)
        session.commit()

    return {
        "status": "success",
        "message": f"Account created for {user.email}. Password setup email sent.",
        # token is handy for testing in Postman/Swagger before email infra is live
        "debug_token": token,
    }
