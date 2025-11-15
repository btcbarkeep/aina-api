from sqlmodel import SQLModel, Field
from typing import Optional

class SignupRequest(SQLModel, table=True):
    __tablename__ = "signup_requests"

    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str
    email: str
    phone: str
    hoa_name: str
    notes: Optional[str] = None
    created_at: Optional[str] = None
