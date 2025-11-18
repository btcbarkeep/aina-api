# models/document.py

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, validator


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
# BASE MODEL (shared fields)
# ======================================================

class DocumentBase(BaseModel):
    """
    Shared fields between create/update/read.
    event_id is OPTIONAL.
    building_id is REQUIRED (documents attach to a building).
    """

    event_id: Optional[UUID] = None                  # Optional FK → events.id
    building_id: UUID                                # Required FK → buildings.id

    s3_key: str                                      # S3 path (required)
    filename: str                                    # File name (required)
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

    # ---------- validators --------------------------------

    @validator("event_id", pre=True)
    def validate_event_id(cls, v):
        return _parse_uuid(v)

    @validator("building_id", pre=True)
    def validate_building_id(cls, v):
        parsed = _parse_uuid(v)
        if parsed is None:
            raise ValueError("building_id must be a valid UUID")
        return parsed


# ======================================================
# CREATE MODEL
# ======================================================

class DocumentCreate(DocumentBase):
    """
    Incoming metadata BEFORE being saved.
    Backend supplies: id, created_at
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

    @validator("event_id", pre=True)
    def validate_event_id(cls, v):
        return _parse_uuid(v)

    @validator("building_id", pre=True)
    def validate_building_id(cls, v):
        return _parse_uuid(v)


# ======================================================
# READ MODEL (Supabase → API response)
# ======================================================

class DocumentRead(DocumentBase):
    id: str                                            # Always return string UUID
    created_at: Optional[datetime] = None

    @validator("created_at", pre=True)
    def parse_created_at(cls, v):
        return _parse_timestamp(v)

    @validator("id", pre=True)
    def convert_id_to_str(cls, v):
        # Supabase often returns UUID objects
        return str(v) if isinstance(v, UUID) else v
