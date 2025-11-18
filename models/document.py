from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, field_validator


# ======================================================
# Helpers to normalize UUIDs and timestamps
# ======================================================

def _parse_uuid(value):
    if not value:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except Exception:
        return None


def _parse_timestamp(value):
    # Normalize timestamps like "2025-01-01T00:00:00Z" → "+00:00"
    if isinstance(value, str) and value.endswith("Z"):
        return value.replace("Z", "+00:00")
    return value


# ======================================================
# BASE MODEL (shared)
# ======================================================

class DocumentBase(BaseModel):
    """
    Shared fields between create/update/read.
    event_id is optional.
    building_id REQUIRED.
    """

    event_id: Optional[UUID] = None
    building_id: UUID

    s3_key: str
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

    # -----------------------------
    # Validators (Pydantic v2)
    # -----------------------------

    @field_validator("event_id", mode="before")
    def validate_event_id(cls, v):
        return _parse_uuid(v)

    @field_validator("building_id", mode="before")
    def validate_building_id(cls, v):
        uuid_val = _parse_uuid(v)
        if uuid_val is None:
            raise ValueError("building_id must be a valid UUID")
        return uuid_val


# ======================================================
# CREATE MODEL
# ======================================================

class DocumentCreate(DocumentBase):
    """
    Incoming metadata BEFORE being saved.
    Backend supplies: id, created_at.
    """
    pass


# ======================================================
# UPDATE MODEL
# ======================================================

class DocumentUpdate(BaseModel):
    event_id: Optional[UUID] = None
    building_id: Optional[UUID] = None
    s3_key: Optional[str] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

    @field_validator("event_id", mode="before")
    def validate_event_id(cls, v):
        return _parse_uuid(v)

    @field_validator("building_id", mode="before")
    def validate_building_id(cls, v):
        return _parse_uuid(v)


# ======================================================
# READ MODEL (Supabase → API response)
# ======================================================

class DocumentRead(DocumentBase):
    id: str
    created_at: Optional[datetime] = None

    @field_validator("created_at", mode="before")
    def parse_created_at(cls, v):
        return _parse_timestamp(v)

    @field_validator("id", mode="before")
    def convert_id_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return str(v)
