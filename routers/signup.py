from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)

from core.supabase_client import get_supabase_client
from core.notifications import send_email
from core.auth_helpers import (
    create_user_no_password,
    generate_password_setup_token,
)

from models.signup import SignupRequestCreate


router = APIRouter(
    prefix="/signup",
    tags=["Signup"],
)


# -----------------------------------------------------
# Helper — Get signup request by UUID
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
# 1️⃣ PUBLIC — Submit signup request
# -----------------------------------------------------
@router.post("/request", summary="Public: Submit signup request")
def request_access(payload: SignupRequestCreate):
    client = get_supabase_client()

    request_data = {
        "full_name": payload.full_name,
        "email": payload.email,
        "phone": payload.phone,
        "organization_name": payload.organization_name,
        "requester_role": payload.requester_role,
        "notes": payload.notes,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
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

    # --- User Notification Email ---
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
            to=payload.email,
        )
    except Exception as e:
        print("Email send failed:", e)

    # --- Admin Notification Email ---
    try:
        send_email(
            subject="New Signup Request - Aina Protocol",
            body=f"""
New signup request received:

Organization: {payload.organization_name or "(none)"}
Role: {payload.requester_role or "(none)"}
Name: {payload.full_name}
Email: {payload.email}
Phone: {payload.phone or "(none)"}

Notes:
{payload.notes or "(none)"}

Request ID: {signup["id"]}
""",
        )
    except Exception as e:
        print("Admin alert email failed:", e)

    return {"status": "success", "request_id": signup["id"]}


# -----------------------------------------------------
# 2️⃣ ADMIN — List all signup requests
# -----------------------------------------------------
@router.get(
    "/requests",
    summary="Admin: List signup requests",
    dependencies=[Depends(requires_role(["admin", "super_admin"]))],
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
# Helper — Enforce role security
# -----------------------------------------------------
def validate_role_assignment(requested_role: str, current_user: CurrentUser):
    """
    Prevent ANY admin from assigning the super_admin role.
    Only super_admin may assign super_admin.
    """

    if requested_role == "super_admin" and current_user.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Only a super_admin can approve or assign the super_admin role.",
        )


# -----------------------------------------------------
# 3️⃣ ADMIN — Approve signup request
# -----------------------------------------------------
@router.post(
    "/requests/{request_id}/approve",
    summary="Admin: Approve signup request",
    dependencies=[Depends(requires_role(["admin", "super_admin"]))],
)
def approve_request(
    request_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    req = get_signup_request_by_id(request_id)

    if req["status"] != "pending":
        raise HTTPException(400, "Request already processed")

    requested_role = req.get("requester_role") or "hoa"

    # 🔐 SECURE ROLE ASSIGNMENT CHECK
    validate_role_assignment(requested_role, current_user)

    # Create user with the SAFE role
    try:
        user = create_user_no_password(
            full_name=req.get("full_name"),
            email=req["email"],
            organization_name=req.get("organization_name"),
            phone=req.get("phone"),
            role=requested_role,
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase user creation error: {e}")

    # Update signup request status
    try:
        client.table("signup_requests").update(
            {
                "status": "approved",
                "approved_at": datetime.utcnow().isoformat(),
            },
            returning="representation",
        ).eq("id", request_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    # Password setup email
    token = generate_password_setup_token(req["email"])

    try:
        send_email(
            subject="Aina Protocol - Create Your Password",
            body=f"""
Aloha {req.get('full_name')},

Your Aina Protocol account has been approved!

Click below to set your password:
https://app.ainaprotocol.com/set-password?token={token}

Mahalo,
Aina Protocol Team
""",
            to=req["email"],
        )
    except Exception as e:
        print("Password setup email failed:", e)

    return {
        "status": "approved",
        "email": req["email"],
        "assigned_role": requested_role,
    }


# -----------------------------------------------------
# 4️⃣ ADMIN — Reject signup request
# -----------------------------------------------------
@router.post(
    "/requests/{request_id}/reject",
    summary="Admin: Reject signup request",
    dependencies=[Depends(requires_role(["admin", "super_admin"]))],
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
        client.table("signup_requests").update(
            {
                "status": "rejected",
                "rejected_at": datetime.utcnow().isoformat(),
            },
            returning="representation",
        ).eq("id", request_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    # Rejection email
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

    return {"status": "rejected", "request_id": request_id}
