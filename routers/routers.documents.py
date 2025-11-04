from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from database import get_session, create_db_and_tables
from models import Document, DocumentCreate, DocumentRead, Event

router = APIRouter(prefix="/documents", tags=["documents"])

@router.on_event("startup")
def startup() -> None:
    create_db_and_tables()

@router.post("/attach", response_model=DocumentRead)
def attach_document(payload: DocumentCreate, session: Session = Depends(get_session)):
    e = session.get(Event, payload.event_id)
    if not e:
        raise HTTPException(status_code=400, detail="Invalid event_id")
    doc = Document.from_orm(payload)
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc

@router.get("", response_model=List[DocumentRead])
def list_documents(event_id: int, session: Session = Depends(get_session)):
    q = select(Document).where(Document.event_id == event_id).order_by(Document.created_at.desc())
    return session.exec(q).all()
