# models/user.py
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


# ===============================================================
# 👤 USER TABLE
# ===============================================================

class User(SQLModel, table=True):
    """
    Local user account table.
    Passwords are optional during admin-invite onboarding.
    """
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    full_name: Optional[str] = None
    hoa_name: Optional[str] = None

    hashed_password: Optional[str] = None  # null = must set password
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


# ===============================================================
# 🔑 PASSWORD RESET / SET-PASSWORD TOKENS
# ===============================================================

class PasswordResetToken(SQLModel, table=True):
    """
    Temporary token for letting HOA users set or reset their password.
    """
    __tablename__ = "password_reset_tokens"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    token: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime


# ===============================================================
# 🏢 USER BUILDING ACCESS
# (already existing, leaving unchanged)
# ===============================================================

class UserBuildingAccess(SQLModel, table=True):
    __tablename__ = "user_building_access"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    building_id: int = Field(foreign_key="buildings.id", index=True)
    role: str = Field(default="hoa", description="hoa, manager, contractor")
