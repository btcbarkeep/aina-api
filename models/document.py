from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# -----------------------------------------
# Base fields (shared across all operations)
# -----------------------------------------
class DocumentBase(BaseModel):
    event_id: Optional[str] = None        # UUID of event (nullable)
    building_id: Optional[str] = None     # UUID of building (nullable)
    s3_key: str                            # S3 path/key
    filename: str                          # Original file name
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None


# -----------------------------------------
# CREATE (same as base)
# -----------------------------------------
class DocumentCreate(DocumentBase):
    pass


# -----------------------------------------
# UPDATE (partial update allowed)
# -----------------------------------------
class DocumentUpdate(BaseModel):
    event_id: Optional[str] = None
    building_id: Optional[str] = None
    s3_key: Optional[str] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None


# -----------------------------------------
# READ (returned from Supabase)
# -----------------------------------------
class DocumentRead(DocumentBase):
    id: str                                # UUID primary key
    created_at: Optional[datetime] = None  # Supabase returns this
