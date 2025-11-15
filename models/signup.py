from sqlmodel import SQLModel, Field
from typing import Optional, Literal
from datetime import datetime

# -----------------------------------------------------
# Incoming public request body (Pydantic model)
# -----------------------------------------------------


class SignupRequestCreate(SQLModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    organization_name: Optional[str] = None

    # Dropdown options shown in Swagger
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
# Database model
# -----------------------------------------------------


class SignupRequest(SQLModel, table=True):
    __tablename__ = "signup_requests"

    id: Optional[int] = Field(default=None, primary_key=True)

    full_name: str
    email: str
    phone: Optional[str] = None
    organization_name: Optional[str] = None

    requester_role: str = Field(default="hoa")
    notes: Optional[str] = None

    # NEW FIELDS
    status: str = Field(default="pending")          # pending, approved, rejected
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
