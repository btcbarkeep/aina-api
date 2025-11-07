from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional

class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    complex: str
    unit: Optional[str] = None
    category: Optional[str] = None
    title: str
    description: Optional[str] = None
    date: datetime = Field(default_factory=datetime.utcnow)
    document_key: Optional[str] = None
    created_by: Optional[str] = None
