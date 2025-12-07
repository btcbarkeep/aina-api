# models/document_email.py

from typing import List
from pydantic import BaseModel, EmailStr, Field, field_validator


class DocumentEmailRequest(BaseModel):
    """Request model for sending documents via email."""
    document_ids: List[str] = Field(
        ..., 
        description="List of document IDs to send (max 5)",
        min_length=1,
        max_length=5
    )
    recipient_emails: List[EmailStr] = Field(
        ...,
        description="List of recipient email addresses",
        min_length=1
    )
    subject: str = Field(
        default="Documents from Aina Protocol",
        description="Email subject line"
    )
    message: str = Field(
        default="",
        description="Optional message to include in the email"
    )
    
    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, v):
        if len(v) > 5:
            raise ValueError("Maximum 5 documents allowed per email")
        if len(v) == 0:
            raise ValueError("At least one document ID is required")
        return v
    
    @field_validator("recipient_emails")
    @classmethod
    def validate_recipient_emails(cls, v):
        if len(v) == 0:
            raise ValueError("At least one recipient email is required")
        return v

