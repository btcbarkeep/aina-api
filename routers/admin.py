# routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import EmailStr

from database import get_session
from dependencies.auth import get_current_user       # 🔒 Protect entire router
from models import UserBuildingAccess
from models.user_create import AdminCreateUser

from core.auth_helpers import (
    create_user_no_password,
    generate_password_setup_token,
)
from core.email_utils import send_password_setup_email


# ---------------------------------------------------------
# 🔐 PROTECT THE ENTIRE ADMIN ROUTER
# ---------------------------------------------------------
router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_user)]          # 👈 every admin route is protected
)


# ---------------------------------------------------------
# Admin: Create user + send password setup email
# ---------------------------------------------------------
@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(
    payload: AdminCreateUser,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),  # still available so we can check role
):
    """
    Admin creates a user with NO password.
    User receives an email to set their password.
    """

    # OPTIONAL: enforce only REAL admins can do this
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    # 1. Create the user record with NO password
    user = create_user_no_password(
        session=session,
        full_name=payload.full_name,
        email=payload.email,
        organization_name=payload.organization_name,
    )

    # 2. Generate one-time password setup token
    token = generate_password_setup_token(payload.email)

    # 3. Send password setup email
    send_password_setup_email(payload.email, token)

    # 4. Assign building + role (optional)
    if payload.building_id is not None:
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
        "debug_token": token,   # remove when email system is fully live
    }
