from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from src.database import get_session
from src.models import Document, DocumentCreate, DocumentRead

router = APIRouter(prefix="/documents", tags=["Documents"])

# 🟢 Create / Attach new document
@router.post("", response_model=DocumentRead)
def attach_document(payload: DocumentCreate, session: Session = Depends(get_session)):
    document = Document.from_orm(payload)
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


# 🟣 List documents (paginated)
@router.get("", response_model=List[DocumentRead])
def list_documents(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    query = select(Document).offset(offset).limit(min(limit, 200))
    return session.exec(query).all()


# 🔵 Get a single document by ID
@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: int, session: Session = Depends(get_session)):
    d = session.get(Document, document_id)
    if not d:
        raise HTTPException(status_code=404, detail="Document not found")
    return d
