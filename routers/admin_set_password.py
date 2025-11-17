from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies.auth import get_current_user, CurrentUser
from core.permission_helpers import requires_permission
from core.supabase_client import get_supabase_client


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(requires_permission("admin:set_password"))],
)


# -----------------------------
# Request model
# -----------------------------
class AdminSetPasswordRequest(BaseModel):
    user_id: str
    new_password: str


# -----------------------------
# POST /auth/admin-set-password
# -----------------------------
@router.post("/admin-set-password")
def admin_set_password(req: AdminSetPasswordRequest,
                       current_user: CurrentUser = Depends(get_current_user)):

    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase client not configured")

    try:
        # Supabase GoTrue API — update user by ID
        result = client.auth.admin.update_user_by_id(
            req.user_id,
            {"password": req.new_password}
        )

        return {
            "success": True,
            "message": "Password updated successfully",
            "user_id": req.user_id,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase error updating password: {e}"
        )
