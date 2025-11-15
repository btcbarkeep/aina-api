# routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel, EmailStr

from database import get_session
from dependencies.auth import get_current_user
from models import User, UserBuildingAccess
from models.user_create import AdminCreateUser

from core.auth_helpers import (
    create_user_no_password,
    generate_password_setup_token,
)
from core.email_utils import send_password_setup_email


# ---------------------------------------------------------
# 🔐 PROTECT ALL ADMIN ROUTES
# ---------------------------------------------------------
router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_user)]
)


# ---------------------------------------------------------
# UTILITY: Require admin role
# ---------------------------------------------------------
def require_admin(user):
    if getattr(user, "role", None) not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admins only")


# ---------------------------------------------------------
# 1️⃣ CREATE USER (No password) + password setup email
# ---------------------------------------------------------
@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(
    payload: AdminCreateUser,
    current_user = Depends(get_current_user)
):
    # Only admins
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    # 1. Create user in Supabase instead of internal DB
    user = create_user_no_password(
        full_name=payload.full_name,
        email=payload.email,
        organization_name=payload.organization_name,
        phone=payload.phone,
        role=payload.role,
    )

    # 2. Create password setup token
    token = generate_password_setup_token(payload.email)

    # 3. Email the token
    send_password_setup_email(payload.email, token)

    return {
        "status": "success",
        "message": f"Account created for {payload.email}. Password setup email sent.",
        "debug_token": token
    }



# ---------------------------------------------------------
# 2️⃣ LIST ALL USERS
# ---------------------------------------------------------
@router.get("/users", summary="Admin: List all users")
def list_users(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    users = session.exec(select(User)).all()
    return users


# ---------------------------------------------------------
# 3️⃣ LIST BUILDING ACCESS FOR A USER
# ---------------------------------------------------------
@router.get("/users/{user_id}/access", summary="Admin: Get building access for a user")
def get_user_access(
    user_id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    rows = session.exec(
        select(UserBuildingAccess).where(UserBuildingAccess.username == user.email)
    ).all()

    return rows


# ---------------------------------------------------------
# 4️⃣ UPDATE USER (name, organization, etc.)
# ---------------------------------------------------------
class AdminUpdateUser(BaseModel):
    full_name: str | None = None
    organization_name: str | None = None
    role: str | None = None   # admin, hoa, contractor, owner, etc.


@router.patch("/users/{user_id}", summary="Admin: Update user")
def update_user(
    user_id: int,
    payload: AdminUpdateUser,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.full_name:
        user.full_name = payload.full_name

    if payload.organization_name:
        user.organization_name = payload.organization_name

    if payload.role:
        user.role = payload.role

    session.add(user)
    session.commit()
    session.refresh(user)

    return {"status": "updated", "user": user}


# ---------------------------------------------------------
# 5️⃣ DELETE USER
# ---------------------------------------------------------
@router.delete("/users/{user_id}", summary="Admin: Delete user")
def delete_user(
    user_id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    session.delete(user)
    session.commit()

    # cleanup building access
    session.exec(
        select(UserBuildingAccess)
        .where(UserBuildingAccess.username == user.email)
    )

    return {"status": "deleted", "email": user.email}


# ---------------------------------------------------------
# 6️⃣ RESEND PASSWORD SETUP EMAIL
# ---------------------------------------------------------
@router.post("/users/{user_id}/resend-password", summary="Admin: Re-send password setup email")
def resend_password_setup(
    user_id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = generate_password_setup_token(user.email)
    send_password_setup_email(user.email, token)

    return {"status": "email_sent", "email": user.email, "debug_token": token}
