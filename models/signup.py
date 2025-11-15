from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


# -----------------------------------------------------
# Incoming public request body (Pydantic model)
# -----------------------------------------------------
class SignupRequestCreate(SQLModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    organization_name: Optional[str] = None
    requester_role: str = "hoa"   # <-- NEW FIELD
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
    created_at: datetime = Field(default_factory=datetime.utcnow)
