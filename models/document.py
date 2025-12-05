from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, field_validator, Field, ConfigDict


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

    event_id: Optional[UUID] = Field(
        None, 
        description="Optional event ID. Get from GET /events endpoint.",
        json_schema_extra={"example": None}
    )
    building_id: UUID = Field(
        ..., 
        description="Building ID. Get from GET /buildings endpoint.",
        json_schema_extra={"example": None}
    )
    
    # Multiple units support (many-to-many via document_units junction table)
    unit_ids: Optional[List[UUID]] = Field(
        None, 
        description="List of unit IDs. Get from GET /buildings/{building_id}/units endpoint.",
        json_schema_extra={"example": None}
    )

    # Multiple contractors support (many-to-many via document_contractors junction table)
    contractor_ids: Optional[List[UUID]] = Field(
        None, 
        description="List of contractor IDs. Get from GET /contractors endpoint.",
        json_schema_extra={"example": None}
    )

    # Category support
    category_id: Optional[UUID] = Field(
        None, 
        description="Optional category ID. Get from categories endpoint.",
        json_schema_extra={"example": None}
    )

    # File metadata (nullable because bulk docs may not be S3 files)
    s3_key: Optional[str] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

    # Bulk-upload field
    document_url: Optional[str] = None

    # Redaction and visibility controls
    is_redacted: Optional[bool] = Field(False, description="Whether the document has been redacted")
    is_public: Optional[bool] = Field(True, description="Whether the document is publicly accessible (true = public, false = private)")

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
    
    Note: Get actual IDs from:
    - building_id: GET /buildings
    - event_id: GET /events (optional)
    - unit_ids: GET /buildings/{building_id}/units (optional)
    - contractor_ids: GET /contractors (optional)
    - category_id: Categories endpoint (optional)
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "building_id": "REPLACE_WITH_ACTUAL_BUILDING_ID",
                "unit_ids": ["REPLACE_WITH_ACTUAL_UNIT_ID"],
                "contractor_ids": ["REPLACE_WITH_ACTUAL_CONTRACTOR_ID"],
                "filename": "example.pdf",
                "content_type": "application/pdf",
                "is_public": True,
                "is_redacted": False
            }
        }
    )


# ======================================================
# UPDATE MODEL
# ======================================================

class DocumentUpdate(BaseModel):
    """
    Used for partial updates to documents. Only include fields you want to change.
    
    Note: To see current values, first GET the document using GET /documents/{document_id},
    then modify only the fields you want to update.
    
    All fields are optional - only include fields you want to change.
    """
    event_id: Optional[UUID] = Field(None, description="Optional event ID. Get current value from GET /documents/{id}")
    building_id: Optional[UUID] = Field(None, description="Optional building ID. Get current value from GET /documents/{id}")
    unit_ids: Optional[List[UUID]] = Field(None, description="List of unit IDs. Get current values from GET /documents/{id}")
    contractor_ids: Optional[List[UUID]] = Field(None, description="List of contractor IDs. Get current values from GET /documents/{id}")
    category_id: Optional[UUID] = Field(None, description="Category ID. Get current value from GET /documents/{id}")

    s3_key: Optional[str] = Field(None, description="S3 key. Get current value from GET /documents/{id}")
    filename: Optional[str] = Field(None, description="Filename. Get current value from GET /documents/{id}")
    content_type: Optional[str] = Field(None, description="Content type. Get current value from GET /documents/{id}")
    size_bytes: Optional[int] = Field(None, description="File size in bytes. Get current value from GET /documents/{id}")
    document_url: Optional[str] = None  # Excluded from DB operations, bulk-only

    # Redaction and visibility controls
    is_redacted: Optional[bool] = Field(None, description="Redaction status. Get current value from GET /documents/{id}")
    is_public: Optional[bool] = Field(None, description="Public visibility. Get current value from GET /documents/{id}")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filename": "updated_filename.pdf",
                "is_public": False
            },
            "description": "Partial update - only include fields you want to change. Get current values from GET /documents/{id} first."
        }
    )

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
