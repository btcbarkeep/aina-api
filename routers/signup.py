from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from datetime import datetime

from database import get_session
from dependencies.auth import get_current_user
from core.notifications import send_email

from models.signup import SignupRequest
from core.auth_helpers import (
    create_user_no_password,
    create_password_token,
)

router = APIRouter(
    prefix="/api/v1/signup",
    tags=["Signup"]
)

# -----------------------------------------------------
# 1️⃣ PUBLIC REQUEST-ACCESS ENDPOINT
# -----------------------------------------------------
@router.post("/request", summary="Public Sign-Up Request")
def request_access(payload: SignupRequest, session: Session = Depends(get_session)):
    """
    Public endpoint where HOA managers request access to Aina Protocol.
    Uses SignupRequest model for full validation.
    """

    # Save request
    payload.created_at = datetime.utcnow()
    payload.status = "pending"

    session.add(payload)
    session.commit()
    session.refresh(payload)

    # Confirmation email to requester
    send_email(
        subject="Aina Protocol - Signup Request Received",
        body=f"""
Aloha {payload.full_name},

Your request to access Aina Protocol has been received.

We will review your request shortly and notify you upon approval.

Mahalo,
Aina Protocol Team
""",
        to=payload.email,
    )

    # Notify Admin (Barry)
    send_email(
        subject="New Signup Request (Aina Protocol)",
        body=f"""
New signup request received:

HOA: {payload.hoa_name}
Name: {payload.full_name}
Email: {payload.email}

Message:
{payload.message or "(none)"}

Request ID: {payload.id}
""",
    )

    return {"status": "success", "request_id": payload.id}


# -----------------------------------------------------
# 2️⃣ LIST ALL SIGNUP REQUESTS (ADMIN ONLY)
# -----------------------------------------------------
@router.get("/requests", summary="List Signup Requests")
def list_requests(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user)
):
    """
    Admin-only: View all signup requests.
    """
    return session.exec(select(SignupRequest)).all()


# -----------------------------------------------------
# 3️⃣ APPROVE SIGNUP REQUEST (ADMIN)
# -----------------------------------------------------
@router.post("/requests/{request_id}/approve", summary="Approve Signup Request")
def approve_request(
    request_id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user)
):
    """
    Approve a signup request, create a user account with NO password,
    and send password setup link.
    """

    req = session.get(SignupRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Signup request not found")

    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Request already processed")

    # Create the user with NO password yet
    new_user = create_user_no_password(
        session=session,
        full_name=req.full_name,
        email=req.email,
        hoa_name=req.hoa_name,
    )

    # Mark the request approved
    req.status = "approved"
    req.approved_at = datetime.utcnow()
    session.add(req)
    session.commit()

    # Generate token for password setup
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
# 4️⃣ REJECT SIGNUP REQUEST (ADMIN)
# -----------------------------------------------------
@router.post("/requests/{request_id}/reject", summary="Reject Signup Request")
def reject_request(
    request_id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user)
):
    """
    Rejects a signup request and emails the user.
    """

    req = session.get(SignupRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Signup request not found")

    req.status = "rejected"
    req.rejected_at = datetime.utcnow()
    session.add(req)
    session.commit()

    send_email(
        subject="Aina Protocol - Signup Request Update",
        body=f"""
Aloha {req.full_name},

We regret to inform you that your request to join Aina Protocol was not approved.

Mahalo,
Aina Protocol Team
""",
        to=req.email,
    )

    return {"status": "rejected"}
