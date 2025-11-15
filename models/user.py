# models/user.py
from typing import Optional
from sqlmodel import SQLModel, Field

class UserBuildingAccess(SQLModel, table=True):
    __tablename__ = "user_building_access"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    building_id: int = Field(foreign_key="buildings.id", index=True)
    role: str = Field(default="hoa", description="hoa, manager, contractor")
