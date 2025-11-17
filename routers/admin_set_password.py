# routers/admin_set_password.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies.auth import get_current_user, CurrentUser
from core.permission_helpers import requires_permission
from core.supabase_client import get_supabase_client


router = APIRouter(
    prefix="/admin",
    tags=["Admin Password Control"],
    dependencies=[Depends(requires_permission("users:reset_password"))],
)


# --------------------------------------------------------------
# Request model
# --------------------------------------------------------------
class AdminSetPasswordRequest(BaseModel):
    user_id: str
    new_password: str


# --------------------------------------------------------------
# POST /admin/set-password
# Requires global permission: users:reset_password
# Only super_admin should typically be granted this permission.
# --------------------------------------------------------------
@router.post("/set-password", summary="Admin: Set a user's password")
def admin_set_password(
    req: AdminSetPasswordRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase client not configured")

    # Optional extra safety (recommended)
    if current_user.role != "super_admin":
        raise HTTPException(
            403,
            "Only a super_admin may reset user passwords."
        )

    try:
        # Supabase Auth Admin — update password
        response = client.auth.admin.update_user_by_id(
            req.user_id,
            {"password": req.new_password}
        )

        return {
            "success": True,
            "user_id": req.user_id,
            "message": "Password updated successfully.",
        }

    except Exception as e:
        raise HTTPException(
            500,
            f"Supabase error updating password: {e}"
        )
