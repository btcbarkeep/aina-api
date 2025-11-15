from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from datetime import datetime

from database import get_session
from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)
from core.notifications import send_email
from models.signup import SignupRequest, SignupRequestCreate

from core.auth_helpers import create_user_no_password, create_password_token


router = APIRouter(
    prefix="/signup",
    tags=["Signup"]
)


# -----------------------------------------------------
# 1️⃣ PUBLIC REQUEST-ACCESS ENDPOINT (NO AUTH)
# -----------------------------------------------------
@router.post("/request", summary="Public Sign-Up Request")
def request_access(
    payload: SignupRequestCreate,
    session: Session = Depends(get_session)
):
    req = SignupRequest(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        organization_name=payload.organization_name,
        requester_role=payload.requester_role,
        notes=payload.notes,
    )

    session.add(req)
    session.commit()
    session.refresh(req)

    # Notify requester
    send_email(
        subject="Aina Protocol - Signup Request Received",
        body=f"""
Aloha {payload.full_name},

Your request to access Aina Protocol has been received.

Mahalo,
Aina Protocol Team
""",
        to=payload.email,
    )

    # Notify admin(s)
    send_email(
        subject="New Signup Request - Aina Protocol",
        body=f"""
New signup request:

Organization: {payload.organization_name}
Role: {payload.requester_role}
Name: {payload.full_name}
Email: {payload.email}
Phone: {payload.phone or "(none)"}

Notes:
{payload.notes or "(none)"}
""",
    )

    return {"status": "success", "request_id": req.id}


# -----------------------------------------------------
# 2️⃣ LIST ALL SIGNUP REQUESTS — ADMIN ONLY
# -----------------------------------------------------
@router.get(
    "/requests",
    summary="List Signup Requests",
    dependencies=[Depends(requires_role(["admin"]))],
)
def list_requests(
    session: Session = Depends(get_session)
):
    return session.exec(select(SignupRequest)).all()


# -----------------------------------------------------
# 3️⃣ APPROVE SIGNUP REQUEST — ADMIN ONLY
# -----------------------------------------------------
@router.post(
    "/requests/{request_id}/approve",
    summary="Approve Signup Request",
    dependencies=[Depends(requires_role(["admin"]))],
)
def approve_request(
    request_id: int,
    session: Session = Depends(get_session),
):
    req = session.get(SignupRequest, request_id)
    if not req:
        raise HTTPException(404, "Signup request not found")

    if req.status != "pending":
        raise HTTPException(400, "Request already processed")

    # Create user without password
    new_user = create_user_no_password(
        session=session,
        full_name=req.full_name,
        email=req.email,
        organization_name=req.organization_name,
    )

    # Mark request approved
    req.status = "approved"
    req.approved_at = datetime.utcnow()
    session.add(req)
    session.commit()

    # Password setup token
    token = create_password_token(
        session=session,
        user_id=new_user.id
    )

    invite_link = f"https://your-domain.com/set-password?token={token}"

    send_email(
        subject="Aina Protocol - Create Your Account Password",
        body=f"""
Aloha {req.full_name},

Your Aina Protocol account has been approved!

Click below to set your password:
{invite_link}

Mahalo,
Aina Protocol Team
""",
        to=req.email,
    )

    return {"status": "approved", "email": req.email}


# -----------------------------------------------------
# 4️⃣ REJECT SIGNUP REQUEST — ADMIN ONLY
# -----------------------------------------------------
@router.post(
    "/requests/{request_id}/reject",
    summary="Reject Signup Request",
    dependencies=[Depends(requires_role(["admin"]))],
)
def reject_request(
    request_id: int,
    session: Session = Depends(get_session),
):
    req = session.get(SignupRequest, request_id)
    if not req:
        raise HTTPException(404, "Signup request not found")

    req.status = "rejected"
    req.rejected_at = datetime.utcnow()
    session.add(req)
    session.commit()

    send_email(
        subject="Aina Protocol - Signup Request Update",
        body=f"""
Aloha {req.full_name},

We regret to inform you that your request to join Aina Protocol 
was not approved.

Mahalo,
Aina Protocol Team
""",
        to=req.email,
    )

    return {"status": "rejected"}
