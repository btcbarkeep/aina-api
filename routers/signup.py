# routers/signup.py

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
        # Let Supabase handle created_at
    }

    # Insert request
    try:
        result = (
            client.table("signup_requests")
            .insert(request_data, returning="representation")
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase insert error: {e}")

    signup = result.data[0]

    # User confirmation email
    try:
        send_email(
            subject="Aina Protocol - Signup Request Received",
            body=f"""
Aloha {payload.full_name},

Your request to access Aina Protocol has been received.
We will review it shortly.

Mahalo,
Aina Protocol Team
""",
            to=email,
        )
    except Exception as e:
        print("Email send failed (user):", e)

    # Admin alert email
    try:
        send_email(
            subject="New Signup Request - Aina Protocol",
            body=f"""
New signup request received:

Organization: {payload.organization_name or "(none)"}
Requested Role: {payload.requester_role or "(none)"}
Name: {payload.full_name}
Email: {email}
Phone: {payload.phone or "(none)"}

Notes:
{payload.notes or "(none)"}

Request ID: {signup['id']}
""",
        )
    except Exception as e:
        print("Admin alert email failed:", e)

    return {"status": "success", "request_id": signup["id"]}


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
# Helper — Validate Role Assignment
# -----------------------------------------------------
def validate_role_assignment(requested_role: str, current_user: CurrentUser):
    if requested_role == "super_admin" and current_user.role != "super_admin":
        raise HTTPException(
            403,
            "Only a super_admin can assign the super_admin role.",
        )


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
    client = get_supabase_client()

    req = get_signup_request_by_id(request_id)

    if req["status"] != "pending":
        raise HTTPException(400, "Request already processed")

    email = req["email"].strip().lower()
    requested_role = req.get("requester_role") or "hoa"

    # Prevent unauthorized role escalation
    validate_role_assignment(requested_role, current_user)

    # Metadata stored in Supabase Auth user record
    metadata = {
        "full_name": req.get("full_name"),
        "organization_name": req.get("organization_name"),
        "phone": req.get("phone"),
        "role": requested_role,
    }

    # -------------------------------------------------
    # Create Supabase Auth User (no password yet)
    # -------------------------------------------------
    try:
        user_resp = client.auth.admin.create_user(
            {
                "email": email,
                "email_confirm": False,
                "user_metadata": metadata,
            }
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase user creation error: {e}")

    # -------------------------------------------------
    # Send password setup email
    # -------------------------------------------------
    try:
        client.auth.admin.invite_user_by_email(email)
    except Exception as e:
        print("Password setup email error:", e)

    # -------------------------------------------------
    # Update signup request status
    # -------------------------------------------------
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

    # Update row
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

    # Notify user
    try:
        send_email(
            subject="Aina Protocol - Signup Request Update",
            body=f"""
Aloha {req.get('full_name')},

Unfortunately, your request to join Aina Protocol
was not approved at this time.

Mahalo,
Aina Protocol Team
""",
            to=req["email"],
        )
    except Exception as e:
        print("Rejection email failed:", e)

    return {
        "status": "rejected",
        "request_id": request_id,
    }
