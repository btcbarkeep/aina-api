# models/user.py

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr
from uuid import UUID


# ===============================================================
# SUPABASE AUTH USER MODELS
# ===============================================================

class UserMetadata(BaseModel):
    """
    Mirrors auth.users.user_metadata (or raw_user_meta_data)
    """
    role: Optional[str] = "aoao"
    full_name: Optional[str] = None
    contractor_id: Optional[UUID] = None
    aoao_organization_id: Optional[UUID] = None
    pm_company_id: Optional[UUID] = None
    organization_name: Optional[str] = None
    email_verified: Optional[bool] = False


class UserBase(BaseModel):
    """
    Base structure used by reads and API responses.
    """
    id: str
    email: EmailStr
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    phone: Optional[str] = None

    # Supabase user metadata
    role: Optional[str] = None
    full_name: Optional[str] = None
    contractor_id: Optional[UUID] = None
    aoao_organization_id: Optional[UUID] = None
    pm_company_id: Optional[UUID] = None
    organization_name: Optional[str] = None
    email_verified: Optional[bool] = False


class UserRead(UserBase):
    """
    Returned to API consumers after normalization.
    """
    pass


class UserCreate(BaseModel):
    """
    Used when admin creates a user via createUser() or inviteUserByEmail()
    """
    email: EmailStr
    full_name: Optional[str] = None
    role: Optional[str] = "aoao"
    contractor_id: Optional[UUID] = None
    aoao_organization_id: Optional[UUID] = None
    pm_company_id: Optional[UUID] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None


class UserUpdate(BaseModel):
    """
    Partial update to user metadata (admin only)
    """
    full_name: Optional[str] = None
    role: Optional[str] = None
    contractor_id: Optional[UUID] = None
    aoao_organization_id: Optional[UUID] = None
    pm_company_id: Optional[UUID] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None
