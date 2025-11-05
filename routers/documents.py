# routers/documents.py
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import uuid4
import os
import boto3
from botocore.exceptions import BotoCoreError, ClientError

router = APIRouter(prefix="/documents", tags=["documents"])

# ---------- Models ----------

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

# Temporary in-memory store for MVP. Replace with DB later.
_FAKE_STORE: List[DocumentOut] = []

# ---------- Routes ----------

@router.post("/attach", response_model=DocumentOut)
def attach_document(body: AttachRequest):
    """
    Persist a record for an uploaded document (MVP: in-memory).
    Replace this later with a real DB insert.
    """
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
    """
    List docs for an event (MVP: from in-memory store).
    """
    return [d for d in _FAKE_STORE if d.event_id == event_id]

@router.get("/download-url")
def get_download_url(s3_key: str):
    """
    Return a short-lived presigned GET URL for the given S3 key.
    Keeps the bucket private while allowing secure downloads.
    """
    bucket = os.getenv("S3_BUCKET")
    region = os.getenv("AWS_REGION")
    if not bucket or not region:
        raise HTTPException(status_code=500, detail="S3 not configured")

    try:
        s3 = boto3.client("s3", region_name=region)
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=600,  # 10 minutes
        )
        return {"url": url}
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to sign: {e}")
