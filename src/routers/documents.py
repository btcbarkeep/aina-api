from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from src.database import get_session
from src.models import Document, DocumentCreate, DocumentRead

router = APIRouter(prefix="/documents", tags=["Documents"])

# 🟢 Create new document
@router.post("/", response_model=DocumentRead)
def attach_document(document_data: DocumentCreate, session: Session = Depends(get_session)):
    """
    Attach a document to an event and store its metadata.
    """
    document = Document.from_orm(document_data)
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


# 🔵 List all documents
@router.get("/", response_model=List[DocumentRead])
def list_documents(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    """
    Retrieve a list of all uploaded documents.
    """
    query = select(Document).offset(offset).limit(min(limit, 200))
    return session.exec(query).all()


# 🟣 Get a single document
@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: int, session: Session = Depends(get_session)):
    """
    Retrieve a single document by ID.
    """
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
