from typing import Optional, List
from pydantic import BaseModel, Field
from uuid import UUID


class RedactionRegion(BaseModel):
    """
    Represents a rectangular region to be redacted in a document.
    Coordinates are normalized (0.0 to 1.0) or pixel-based depending on mode.
    """
    x: float = Field(..., description="X coordinate (left)")
    y: float = Field(..., description="Y coordinate (top)")
    width: float = Field(..., description="Width of the redaction region")
    height: float = Field(..., description="Height of the redaction region")
    page_number: Optional[int] = Field(None, description="Page number (for multi-page documents)")
    reason: Optional[str] = Field(None, description="Reason for redaction (e.g., 'PII', 'SSN', 'Address')")


class RedactionCreate(BaseModel):
    """
    Model for creating a redaction record.
    """
    document_id: UUID
    regions: List[RedactionRegion] = Field(default_factory=list, description="List of regions to redact")
    redaction_type: Optional[str] = Field(None, description="Type of redaction (e.g., 'automatic', 'manual', 'ai')")
    status: Optional[str] = Field("pending", description="Status of redaction (pending, processing, completed, failed)")
    notes: Optional[str] = Field(None, description="Additional notes about the redaction")


class RedactionUpdate(BaseModel):
    """
    Model for updating a redaction record.
    """
    regions: Optional[List[RedactionRegion]] = None
    redaction_type: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class RedactionRead(BaseModel):
    """
    Model for reading a redaction record.
    """
    id: str
    document_id: str
    regions: List[RedactionRegion] = Field(default_factory=list)
    redaction_type: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None
