from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, field_validator, Field


# ======================================================
# Helpers
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
    if isinstance(value, str) and value.endswith("Z"):
        return value.replace("Z", "+00:00")
    return value


# ======================================================
# BASE MODEL
# ======================================================

class DocumentBase(BaseModel):
    """
    Shared fields for create/update/read.
    building_id REQUIRED for direct uploads.
    event_id is optional.
    """

    event_id: Optional[UUID] = None
    building_id: UUID
    
    # Multiple units support (many-to-many via document_units junction table)
    unit_ids: Optional[List[UUID]] = Field(None, description="List of unit IDs associated with this document")

    # Multiple contractors support (many-to-many via document_contractors junction table)
    contractor_ids: Optional[List[UUID]] = Field(None, description="List of contractor IDs associated with this document")

    # Category support
    category_id: Optional[UUID] = Field(None, description="Category ID for this document")

    # File metadata (nullable because bulk docs may not be S3 files)
    s3_key: Optional[str] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

    # Bulk-upload field
    document_url: Optional[str] = None

    # Redaction and visibility controls
    is_redacted: Optional[bool] = Field(False, description="Whether the document has been redacted")
    is_public: Optional[bool] = Field(False, description="Whether the document is publicly accessible (false = private)")

    # -----------------------------
    # Validators
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

    @field_validator("unit_ids", mode="before")
    def validate_unit_ids(cls, v):
        if not v:
            return None
        if not isinstance(v, list):
            return None
        result = []
        for item in v:
            parsed = _parse_uuid(item)
            if parsed:
                result.append(parsed)
        return result if result else None

    @field_validator("contractor_ids", mode="before")
    def validate_contractor_ids(cls, v):
        if not v:
            return None
        if not isinstance(v, list):
            return None
        result = []
        for item in v:
            parsed = _parse_uuid(item)
            if parsed:
                result.append(parsed)
        return result if result else None

    @field_validator("category_id", mode="before")
    def validate_category_id(cls, v):
        return _parse_uuid(v)


# ======================================================
# CREATE MODEL
# ======================================================

class DocumentCreate(DocumentBase):
    """
    Used when creating documents from uploads or bulk imports.
    """
    pass


# ======================================================
# UPDATE MODEL
# ======================================================

class DocumentUpdate(BaseModel):
    event_id: Optional[UUID] = None
    building_id: Optional[UUID] = None
    unit_ids: Optional[List[UUID]] = Field(None, description="List of unit IDs associated with this document")
    contractor_ids: Optional[List[UUID]] = Field(None, description="List of contractor IDs associated with this document")
    category_id: Optional[UUID] = Field(None, description="Category ID for this document")

    s3_key: Optional[str] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    document_url: Optional[str] = None

    # Redaction and visibility controls
    is_redacted: Optional[bool] = None
    is_public: Optional[bool] = None

    @field_validator("event_id", mode="before")
    def validate_event_id(cls, v):
        return _parse_uuid(v)

    @field_validator("building_id", mode="before")
    def validate_building_id(cls, v):
        return _parse_uuid(v)

    @field_validator("category_id", mode="before")
    def validate_category_id(cls, v):
        return _parse_uuid(v)

    @field_validator("unit_ids", mode="before")
    def validate_unit_ids(cls, v):
        if not v:
            return None
        if not isinstance(v, list):
            return None
        result = []
        for item in v:
            parsed = _parse_uuid(item)
            if parsed:
                result.append(parsed)
        return result if result else None

    @field_validator("contractor_ids", mode="before")
    def validate_contractor_ids(cls, v):
        if not v:
            return None
        if not isinstance(v, list):
            return None
        result = []
        for item in v:
            parsed = _parse_uuid(item)
            if parsed:
                result.append(parsed)
        return result if result else None

    @field_validator("category_id", mode="before")
    def validate_category_id(cls, v):
        return _parse_uuid(v)


# ======================================================
# READ MODEL
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
