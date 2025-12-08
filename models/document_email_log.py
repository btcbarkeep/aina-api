# models/document_email_log.py

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr


class DocumentEmailLogRead(BaseModel):
    """Read model for document email logs."""
    id: str
    sender_user_id: str
    sender_email: str
    sender_name: Optional[str] = None
    recipient_emails: List[str]
    document_ids: List[str]
    subject: str
    message: Optional[str] = None
    status: str  # 'sent', 'failed', 'partial'
    error_message: Optional[str] = None
    sent_at: datetime
    created_at: datetime
    updated_at: datetime
    
    # Enriched fields (optional, added by endpoint)
    document_titles: Optional[List[str]] = None
    sender_full_name: Optional[str] = None
    
    model_config = {"from_attributes": True}

