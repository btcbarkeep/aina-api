from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from database import get_session
from core.notifications import send_email
from models.signup import SignupRequest, SignupRequestCreate

router = APIRouter(
    prefix="/api/v1/signup",
    tags=["Signup"]
)

# -----------------------------------------------------
# 1️⃣ PUBLIC REQUEST-ACCESS ENDPOINT (WITH MODEL)
# -----------------------------------------------------
@router.post("/request", summary="Public Sign-Up Request")
def request_access(payload: SignupRequestCreate, session: Session = Depends(get_session)):

    req = SignupRequest(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        organization_name=payload.organization_name,
        requester_role=payload.requester_role,
        notes=payload.notes,
        message=payload.notes,   # backward compatibility
    )

    session.add(req)
    session.commit()
    session.refresh(req)

    # Confirmation email to requester
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

    # Notify admin (Barry)
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
        organization_name=req.organization_name,   # 👈 UPDATED
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
