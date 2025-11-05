from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import uuid4

router = APIRouter(prefix="/documents", tags=["documents"])

class AttachRequest(BaseModel):
    event_id: int = Field(..., description="ID of the event this document belongs to")
    s3_key: str = Field(..., description="S3 object key returned by /upload/url")
    filename: str
    content_type: str
    size_bytes: Optional[int] = None

class DocumentOut(BaseModel):
    id: str
    event_id: int
    s3_key: str
    filename: str
    content_type: str
    size_bytes: Optional[int] = None

# Temporary in-memory store so the GET route works during MVP testing
_FAKE_STORE: List[DocumentOut] = []

@router.post("/attach", response_model=DocumentOut)
def attach_document(body: AttachRequest):
    # TODO: replace this block with a DB insert when your models are ready.
    doc = DocumentOut(
        id=uuid4().hex,
        event_id=body.event_id,
        s3_key=body.s3_key,
        filename=body.filename,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
    )
    _FAKE_STORE.append(doc)
    return doc

@router.get("", response_model=List[DocumentOut])
def list_documents(event_id: int = Query(..., description="Filter by event_id")):
    # TODO: replace with a DB query
    return [d for d in _FAKE_STORE if d.event_id == event_id]

