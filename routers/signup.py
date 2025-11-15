from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from datetime import datetime

from database import get_session
from dependencies.auth import get_current_user
from core.notifications import send_email
from models.signup import SignupRequest


from core.auth_helpers import create_user_no_password, create_password_token

router = APIRouter(
    prefix="/api/v1/signup",
    tags=["Signup"]
)

# -----------------------------------------------------
# 1️⃣ PUBLIC REQUEST-ACCESS ENDPOINT
# -----------------------------------------------------
@router.post("/request", summary="Public Sign-Up Request")
def request_access(payload: dict, session: Session = Depends(get_session)):
    """
    Public endpoint where HOA managers request access to Aina Protocol.
    Does NOT create a user yet — requires admin approval.
    """
    hoa_name = payload.get("hoa_name")
    full_name = payload.get("full_name")
    email = payload.get("email")
    message = payload.get("message")

    if not hoa_name or not full_name or not email:
        raise HTTPException(status_code=400, detail="hoa_name, full_name, and email are required")

    # Save request
    req = SignupRequest(
        hoa_name=hoa_name,
        full_name=full_name,
        email=email,
        message=message,
    )
    session.add(req)
    session.commit()
    session.refresh(req)

    # Confirmation email to requester
    send_email(
        subject="Aina Protocol - Signup Request Received",
        body=f"""
Aloha {full_name},

Your request to access Aina Protocol has been received.

We will review your request shortly and notify you upon approval.

Mahalo,
Aina Protocol Team
""",
        to=email,
    )

    # Notify Barry/Admin
    send_email(
        subject="New Signup Request (Aina Protocol)",
        body=f"""
New signup request:

HOA: {hoa_name}
Name: {full_name}
Email: {email}

Message:
{message or "(none)"}
""",
    )

    return {"status": "success", "request_id": req.id}


# -----------------------------------------------------
# 2️⃣ LIST ALL SIGNUP REQUESTS (ADMIN ONLY)
# -----------------------------------------------------
@router.get("/requests", summary="List Signup Requests")
def list_requests(session: Session = Depends(get_session), current_user=Depends(get_current_user)):
    """
    Admin-only view of all signup requests.
    """
    requests = session.exec(select(SignupRequest)).all()
    return requests


# -----------------------------------------------------
# 3️⃣ APPROVE SIGNUP REQUEST (ADMIN)
# -----------------------------------------------------
@router.post("/requests/{request_id}/approve", summary="Approve Signup Request")
def approve_request(request_id: int, session: Session = Depends(get_session), current_user=Depends(get_current_user)):
    """
    Converts a SignupRequest into an actual user account and sends the password invite email.
    """
    req = session.get(SignupRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Signup request not found")

    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Request already processed")

    # Create user WITHOUT password yet
    user = create_user_no_password(
        session=session,
        full_name=req.full_name,
        email=req.email,
        hoa_name=req.hoa_name,
    )

    # Mark approved
    req.status = "approved"
    req.approved_at = datetime.utcnow()
    session.add(req)
    session.commit()

    # Create reset token for password creation
    token = create_password_token(req.email)

    invite_link = f"https://your-domain.com/set-password?token={token}"

    send_email(
        subject="Aina Protocol - Create Your Account Password",
        body=f"""
Aloha {req.full_name},

Your Aina Protocol account has been approved!

Click the link below to create your password:

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
def reject_request(request_id: int, session: Session = Depends(get_session), current_user=Depends(get_current_user)):
    """
    Marks a request as rejected and notifies the requester.
    """
    req = session.get(SignupRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Signup request not found")

    req.status = "rejected"
    session.add(req)
    session.commit()

    send_email(
        subject="Aina Protocol - Signup Request Update",
        body=f"Aloha {req.full_name},\n\nYour request to join Aina Protocol has been rejected.",
        to=req.email,
    )

    return {"status": "rejected"}
