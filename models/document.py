# models/document.py
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

class DocumentBase(SQLModel):
    event_id: int = Field(foreign_key="events.id", index=True)
    s3_key: str
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

class Document(DocumentBase, table=True):
    __tablename__ = "documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class DocumentCreate(DocumentBase):
    pass

class DocumentRead(DocumentBase):
    id: int
    created_at: datetime

class DocumentUpdate(SQLModel):
    event_id: Optional[int] = None
    s3_key: Optional[str] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
