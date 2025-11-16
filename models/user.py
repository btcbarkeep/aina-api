# models/user.py
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr


# ===================================================================
# 👤 USER MODELS (Supabase table: users)
# ===================================================================

class UserBase(BaseModel):
    full_name: Optional[str] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = "hoa"                 # default HOA role
    email: EmailStr


# Returned when reading a user from Supabase
class UserRead(UserBase):
    id: str                            # UUID from Supabase
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# Used when creating a user WITHOUT password (admin invite flow)
class UserCreate(BaseModel):
    full_name: Optional[str] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = "hoa"
    email: EmailStr


# Partial updates allowed (admin)
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
