# routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from database import get_session
from models.user_create import AdminCreateUser
from models import UserBuildingAccess
from core.auth_helpers import (
    create_user_no_password,
    generate_password_setup_token,
)
from core.email_utils import send_password_setup_email

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])



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
@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(
    payload: AdminCreateUser,
    session: Session = Depends(get_session),
):
    """
    Admin creates a user with NO password.
    User receives an email to set their password.
    """

    # 1. Create the user record (no password)
    user = create_user_no_password(
        session=session,
        full_name=payload.full_name,
        email=payload.email,
        organization_name=payload.organization_name,   # UPDATED
    )

    # 2. Generate one-time password setup token
    token = generate_password_setup_token(payload.email)

    # 3. Send password setup email
    send_password_setup_email(payload.email, token)

    # 4. Assign initial building + role
    access = UserBuildingAccess(
        username=payload.email,
        building_id=payload.building_id,
        role=payload.role,
    )
    session.add(access)
    session.commit()

    return {
        "status": "success",
        "message": f"Account created for {payload.email}. Password setup email sent.",
        "debug_token": token,
    }
