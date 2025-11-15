from sqlmodel import SQLModel, Field
from datetime import datetime

class SignupRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    hoa_name: str
    full_name: str
    email: str
    message: str | None = None

    status: str = Field(default="pending")  # pending, approved, rejected
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: datetime | None = None
