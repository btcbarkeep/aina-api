from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DocumentBase(BaseModel):
    event_id: str
    s3_key: str
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    event_id: Optional[str] = None
    s3_key: Optional[str] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None


class DocumentRead(DocumentBase):
    id: str
    created_at: datetime

    class Config:
        orm_mode = True
