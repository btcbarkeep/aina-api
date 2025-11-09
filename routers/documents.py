# routers/documents.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List

from database import get_session
from models import Document, DocumentCreate, DocumentRead  # ✅ fixed import
from dependencies.auth import get_current_user

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)

"""
Document endpoints handle storage, retrieval, and management of AOAO and property
documents including minutes, rules, reports, and financial disclosures.
"""


# 🟢 Attach (admin only)
@router.post("/", response_model=DocumentRead)
def attach_document(
    payload: DocumentCreate,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    """Upload or attach a new AOAO document (protected)."""
    document = Document.from_orm(payload)
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


# 🟣 List (public)
@router.get("/", response_model=List[DocumentRead])
def list_documents(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    """List all documents (public)."""
    query = select(Document).offset(offset).limit(min(limit, 200))
    return session.exec(query).all()


# 🔵 Get by ID (public)
@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: int,
    session: Session = Depends(get_session),
):
    """Retrieve a document by its ID."""
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
