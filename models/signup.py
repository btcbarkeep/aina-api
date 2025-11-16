from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime


# -----------------------------------------------------
# Incoming public request body (request DTO)
# -----------------------------------------------------
class SignupRequestCreate(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    organization_name: Optional[str] = None

    requester_role: Literal[
        "hoa",
        "property_manager",
        "owner",
        "contractor",
        "vendor",
        "tenant",
        "buyer",
        "seller",
        "other"
    ] = "hoa"

    notes: Optional[str] = None


# -----------------------------------------------------
# Response model — mirrors Supabase row
# -----------------------------------------------------
class SignupRequest(BaseModel):
    id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    organization_name: Optional[str] = None

    requester_role: str = "hoa"
    notes: Optional[str] = None

    status: str = "pending"     # pending, approved, rejected
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None

    created_at: datetime
