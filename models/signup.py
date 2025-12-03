from pydantic import BaseModel, EmailStr
from typing import Optional, Literal
from datetime import datetime


# --------------------------------------------------------------------
# ROLES allowed to request signup (public-facing request form)
# Must match real RBAC roles from your system.
# --------------------------------------------------------------------
SignupAllowedRoles = Literal[
    "aoao",
    "property_manager",
    "owner",
    "contractor",
    "contractor_staff",
    "vendor",
    "tenant",
    "buyer",
    "seller",
    "other"
]


# --------------------------------------------------------------------
# PUBLIC REQUEST BODY — What the public form sends to your backend
# --------------------------------------------------------------------
class SignupRequestCreate(BaseModel):
    full_name: str
    email: EmailStr             # FIX: real email validation
    phone: Optional[str] = None
    organization_name: Optional[str] = None

    requester_role: SignupAllowedRoles = "aoao"
    notes: Optional[str] = None


# --------------------------------------------------------------------
# SUPABASE ROW → API RESPONSE
# What your API returns when listing Signup Requests
# --------------------------------------------------------------------
class SignupRequest(BaseModel):
    id: int

    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    organization_name: Optional[str] = None

    requester_role: str = "aoao"
    notes: Optional[str] = None

    # System populated
    status: str = "pending"     # pending, approved, rejected
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None

    created_at: datetime
