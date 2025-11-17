# routers/signup.py

from core.config import settings


from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from core.notifications import send_email
from models.signup import SignupRequestCreate

router = APIRouter(
    prefix="/signup",
    tags=["Signup"],
)

# -----------------------------------------------------
# Helper — Fetch Signup Request
# -----------------------------------------------------
def get_signup_request_by_id(request_id: str):
    client = get_supabase_client()

    try:
        result = (
            client.table("signup_requests")
            .select("*")
            .eq("id", request_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase query error: {e}")

    if not result.data:
        raise HTTPException(404, "Signup request not found")

    return result.data


# -----------------------------------------------------
# 1️⃣ PUBLIC — Submit Signup Request
# -----------------------------------------------------
@router.post("/request", summary="Public: Submit signup request")
def request_access(payload: SignupRequestCreate):
    client = get_supabase_client()

    email = payload.email.strip().lower()

    request_data = {
        "full_name": payload.full_name,
        "email": email,
        "phone": payload.phone,
        "organization_name": payload.organization_name,
        "requester_role": payload.requester_role,
        "notes": payload.notes,
        "status": "pending",
    }

    try:
        result = (
            client.table("signup_requests")
            .insert(request_data, returning="representation")
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase insert error: {e}")

    signup = result.data[0]

    # Optional emails
    try:
        send_email(
            subject="Aina Protocol - Signup Request Received",
            body=f"Aloha {payload.full_name},\n\nWe received your request.\n\nMahalo!",
            to=email,
        )
    except Exception:
        pass

    return {"status": "success", "request_id": signup["id"]}


# -----------------------------------------------------
# Helper — Validate Role Assignment
# -----------------------------------------------------
def validate_role_assignment(requested_role: str, current_user: CurrentUser):
    if requested_role == "super_admin" and current_user.role != "super_admin":
        raise HTTPException(
            403,
            "Only a super_admin can assign the super_admin role.",
        )


# -----------------------------------------------------
# 2️⃣ ADMIN — List Signup Requests
# -----------------------------------------------------
@router.get(
    "/requests",
    summary="Admin: List signup requests",
    dependencies=[Depends(requires_permission("access:read"))],
)
def list_requests():
    client = get_supabase_client()

    try:
        result = (
            client.table("signup_requests")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        raise HTTPException(500, f"Supabase fetch error: {e}")


# -----------------------------------------------------
# 3️⃣ ADMIN — Approve Signup Request
# -----------------------------------------------------
@router.post(
    "/requests/{request_id}/approve",
    summary="Admin: Approve signup request",
    dependencies=[Depends(requires_permission("access:write"))],
)
def approve_request(
    request_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()  # ✔ ALWAYS service role key

    print("🔑 USING KEY:", settings.SUPABASE_SERVICE_ROLE_KEY[:6], "********")
    
    req = get_signup_request_by_id(request_id)

    if req["status"] != "pending":
        raise HTTPException(400, "Request already processed")

    email = req["email"].strip().lower()
    requested_role = req.get("requester_role") or "hoa"

    validate_role_assignment(requested_role, current_user)

    metadata = {
        "full_name": req.get("full_name"),
        "organization_name": req.get("organization_name"),
        "phone": req.get("phone"),
        "role": requested_role,
        "permissions": [],
        "contractor_id": None,
    }

    # ---- 100% FIX: use service-role ONLY ----
    try:
        user_resp = client.auth.admin.create_user(
            email=email,
            email_confirm=False,
            user_metadata=metadata,
        )

    except Exception as e:
        raise HTTPException(500, f"Supabase user creation error: {e}")

    # Send invite - OK if already exists
    try:
        client.auth.admin.invite_user_by_email(email)
    except Exception:
        pass

    # Update signup request status
    try:
        (
            client.table("signup_requests")
            .update(
                {
                    "status": "approved",
                    "approved_at": datetime.utcnow().isoformat(),
                },
                returning="representation",
            )
            .eq("id", request_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    return {
        "status": "approved",
        "email": email,
        "assigned_role": requested_role,
    }


# -----------------------------------------------------
# 4️⃣ ADMIN — Reject Signup Request
# -----------------------------------------------------
@router.post(
    "/requests/{request_id}/reject",
    summary="Admin: Reject signup request",
    dependencies=[Depends(requires_permission("access:write"))],
)
def reject_request(
    request_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    req = get_signup_request_by_id(request_id)

    if req["status"] != "pending":
        raise HTTPException(400, "Request already processed")

    try:
        (
            client.table("signup_requests")
            .update(
                {
                    "status": "rejected",
                    "rejected_at": datetime.utcnow().isoformat(),
                },
                returning="representation",
            )
            .eq("id", request_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    return {
        "status": "rejected",
        "request_id": request_id,
    }
