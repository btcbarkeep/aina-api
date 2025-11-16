from typing import Optional
from pydantic import BaseModel, EmailStr

class AdminCreateUser(BaseModel):
    full_name: Optional[str] = None
    email: EmailStr
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = "hoa"
