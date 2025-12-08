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

    event_id: Optional[UUID] = Field(None, description="Optional event ID. Get from GET /events endpoint.")
    building_id: UUID = Field(..., description="Building ID. Get from GET /buildings endpoint.")
    
    # Multiple units support (many-to-many via document_units junction table)
    unit_ids: Optional[List[UUID]] = Field(None, description="List of unit IDs. Get from GET /buildings/{building_id}/units endpoint.")

    # Multiple contractors support (many-to-many via document_contractors junction table)
    contractor_ids: Optional[List[UUID]] = Field(None, description="List of contractor IDs. Get from GET /contractors endpoint.")

    # Category and subcategory support
    category_id: Optional[UUID] = Field(None, description="Optional category ID from document_categories table. Get from GET /categories endpoint.")
    subcategory_id: Optional[UUID] = Field(None, description="Optional subcategory ID from document_subcategories table. Get from GET /categories endpoint.")

    # Document title (required) and file metadata
    title: str = Field(..., description="Document title (required)")
    s3_key: Optional[str] = None
    size_bytes: Optional[int] = None
    # Note: filename is auto-generated from title for database compatibility

    # Bulk-upload field
    document_url: Optional[str] = None

    # Redaction and visibility controls
    is_redacted: Optional[bool] = Field(False, description="Whether the document has been redacted")
    is_public: Optional[bool] = Field(True, description="Whether the document is publicly accessible (true = public, false = private)")
    
    # Uploader information (denormalized for performance)
    uploaded_by: Optional[str] = Field(None, description="User ID who uploaded the document")
    uploaded_by_role: Optional[str] = Field(None, description="Role of the user who uploaded the document (denormalized)")

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
    - category_id: GET /categories endpoint (optional) - UUID from document_categories table
    - subcategory_id: GET /categories endpoint (optional) - UUID from document_subcategories table
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "building_id": "REPLACE_WITH_ACTUAL_BUILDING_ID",
                "unit_ids": ["REPLACE_WITH_ACTUAL_UNIT_ID"],
                "contractor_ids": ["REPLACE_WITH_ACTUAL_CONTRACTOR_ID"],
                "category_id": "REPLACE_WITH_ACTUAL_CATEGORY_ID",
                "subcategory_id": "REPLACE_WITH_ACTUAL_SUBCATEGORY_ID",
                "title": "Example Document Title",
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
    category_id: Optional[UUID] = Field(None, description="Category ID from document_categories table. Get current value from GET /documents/{id}")
    subcategory_id: Optional[UUID] = Field(None, description="Subcategory ID from document_subcategories table. Get current value from GET /documents/{id}")

    title: Optional[str] = Field(None, description="Document title. Get current value from GET /documents/{id}")
    s3_key: Optional[str] = Field(None, description="S3 key. Get current value from GET /documents/{id}")
    size_bytes: Optional[int] = Field(None, description="File size in bytes. Get current value from GET /documents/{id}")
    # Note: filename is auto-generated from title for database compatibility
    document_url: Optional[str] = None  # Excluded from DB operations, bulk-only

    # Redaction and visibility controls
    is_redacted: Optional[bool] = Field(None, description="Redaction status. Get current value from GET /documents/{id}")
    is_public: Optional[bool] = Field(None, description="Public visibility. Get current value from GET /documents/{id}")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_id": None,
                "building_id": None,
                "unit_ids": None,
                "contractor_ids": None,
                "category_id": None,
                "subcategory_id": None,
                "title": "Updated Document Title",
                "s3_key": None,
                "size_bytes": 1024,
                "is_redacted": False,
                "is_public": True
            }
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
    uploaded_by_name: Optional[str] = Field(None, description="Name of the user who uploaded the document (fetched from user metadata)")
    created_at: Optional[datetime] = None

    @field_validator("created_at", mode="before")
    def parse_created_at(cls, v):
        return _parse_timestamp(v)

    @field_validator("id", mode="before")
    def convert_id_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return str(v)
