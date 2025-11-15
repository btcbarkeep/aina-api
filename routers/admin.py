# routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel, EmailStr

from database import get_session
from dependencies.auth import get_current_user
from models import UserBuildingAccess

from core.supabase_client import get_supabase_client
from core.auth_helpers import (
    create_user_no_password,
    generate_password_setup_token,
)
from core.email_utils import send_password_setup_email


# ---------------------------------------------------------
# 🔐 PROTECT ENTIRE ROUTER WITH AUTH
# ---------------------------------------------------------
router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_user)]
)


# ---------------------------------------------------------
# UTILITY: ADMIN CHECK
# ---------------------------------------------------------
def require_admin(user):
    if getattr(user, "role", None) not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admins only")


# ---------------------------------------------------------
# 1️⃣ CREATE USER — stored in Supabase
# ---------------------------------------------------------
@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(
    payload,
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    # 1. Create user in Supabase
    supa_user = create_user_no_password(
        full_name=payload.full_name,
        email=payload.email,
        organization_name=payload.organization_name,
        phone=payload.phone,
        role=payload.role,
    )

    # 2. Create token
    token = generate_password_setup_token(payload.email)

    # 3. Send email
    send_password_setup_email(payload.email, token)

    return {
        "status": "success",
        "message": f"Account created for {payload.email}. Password setup email sent.",
        "debug_token": token,
    }


# ---------------------------------------------------------
# 2️⃣ LIST ALL USERS (Supabase)
# ---------------------------------------------------------
@router.get("/users", summary="Admin: List all users")
def list_users(current_user=Depends(get_current_user)):
    require_admin(current_user)

    client = get_supabase_client()

    result = client.table("users").select("*").execute()

    if result.error:
        raise HTTPException(status_code=500, detail="Supabase error fetching users")

    return result.data


# ---------------------------------------------------------
# 3️⃣ LIST BUILDING ACCESS FOR USER (local table)
# ---------------------------------------------------------
@router.get("/users/{user_id}/access", summary="Admin: Get building access for a user")
def get_user_access(
    user_id: str,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    # Fetch Supabase user by id
    client = get_supabase_client()
    user_res = client.table("users").select("*").eq("id", user_id).maybe_single().execute()

    if not user_res.data:
        raise HTTPException(status_code=404, detail="User not found")

    email = user_res.data["email"]

    # Fetch access rows from local DB
    rows = session.exec(
        select(UserBuildingAccess).where(UserBuildingAccess.username == email)
    ).all()

    return rows


# ---------------------------------------------------------
# 4️⃣ UPDATE USER (Supabase)
# ---------------------------------------------------------
class AdminUpdateUser(BaseModel):
    full_name: str | None = None
    organization_name: str | None = None
    role: str | None = None
    phone: str | None = None


@router.patch("/users/{user_id}", summary="Admin: Update user")
def update_user(
    user_id: str,
    payload: AdminUpdateUser,
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    client = get_supabase_client()

    update_data = {k: v for k, v in payload.dict().items() if v is not None}
    update_data["updated_at"] = "now()"

    result = client.table("users").update(update_data).eq("id", user_id).execute()

    if result.error:
        raise HTTPException(status_code=500, detail=f"Supabase error: {result.error}")

    return {"status": "updated", "user": result.data}


# ---------------------------------------------------------
# 5️⃣ DELETE USER (Supabase + clear access locally)
# ---------------------------------------------------------
@router.delete("/users/{user_id}", summary="Admin: Delete user")
def delete_user(
    user_id: str,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)
    client = get_supabase_client()

    # Fetch email to clean local access
    res = client.table("users").select("*").eq("id", user_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="User not found")

    email = res.data["email"]

    # Delete user from Supabase
    delete_res = client.table("users").delete().eq("id", user_id).execute()
    if delete_res.error:
        raise HTTPException(status_code=500, detail=f"Supabase error: {delete_res.error}")

    # Cleanup building access locally
    session.exec(
        select(UserBuildingAccess).where(UserBuildingAccess.username == email)
    )
    session.commit()

    return {"status": "deleted", "email": email}


# ---------------------------------------------------------
# 6️⃣ RESEND PASSWORD SETUP EMAIL (Supabase)
# ---------------------------------------------------------
@router.post("/users/{user_id}/resend-password", summary="Admin: Re-send password setup email")
def resend_password_setup(
    user_id: str,
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    client = get_supabase_client()
    user_res = client.table("users").select("*").eq("id", user_id).maybe_single().execute()

    if not user_res.data:
        raise HTTPException(status_code=404, detail="User not found")

    email = user_res.data["email"]

    token = generate_password_setup_token(email)
    send_password_setup_email(email, token)

    return {"status": "email_sent", "email": email, "debug_token": token}
