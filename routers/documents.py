# routers/documents.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
import traceback

from database import get_session
from dependencies.auth import get_current_user
from models.document import (
    Document,
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
)

from models.event import Event
from models.building import Building
from models.user_access import UserBuildingAccess


from core.supabase_client import get_supabase_client
from core.supabase_helpers import update_record

from core.auth_helpers import verify_user_building_access


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


"""
Documents manage metadata only (event attachments, HOA documents, etc.).
Actual binary files live in S3 or Supabase storage.
We sync metadata to Supabase, not the file content.
"""

# -----------------------------------------------------
# SUPABASE INTEGRATION
# -----------------------------------------------------

@router.get("/supabase", summary="List Documents from Supabase")
def list_documents_supabase(limit: int = 50):
    """Fetch documents directly from Supabase for debugging."""
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        result = client.table("documents").select("*").limit(limit).execute()
        return result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")


@router.post(
    "/supabase",
    response_model=DocumentRead,
    summary="Create Document in Supabase (w/ permission check)"
)
def create_document_supabase(
    payload: DocumentCreate,
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # Ensure the associated event exists
    event = session.get(Event, payload.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Associated event not found")

    # Permission check (uses building_id from event)
    verify_user_building_access(session, current_user, event.building_id)

    try:
        result = client.table("documents").insert(payload.dict()).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Supabase insert failed")
        return result.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")


@router.put("/supabase/{document_id}", summary="Update Document in Supabase")
def update_document_supabase(document_id: str, payload: DocumentUpdate):
    update_data = payload.dict(exclude_unset=True)

    result = update_record("documents", document_id, update_data)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]

@router.delete("/supabase/{document_id}", summary="Delete Document (Supabase)", tags=["Documents"])
def delete_document_supabase(
    document_id: int,
    current_user: str = Depends(get_current_user),
):
    """
    Delete a document record from Supabase by ID.
    Prevents broken relations and ensures clean metadata removal.
    """

    from core.supabase_client import get_supabase_client
    client = get_supabase_client()

    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # --- Delete the record ---
    try:
        result = (
            client
            .table("documents")
            .delete()
            .eq("id", document_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Document not found in Supabase")

        return {
            "status": "deleted",
            "id": document_id,
            "message": f"Document {document_id} successfully deleted from Supabase.",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase delete error: {e}")


# -----------------------------------------------------
# LOCAL DOCUMENT CRUD
# -----------------------------------------------------

@router.post(
    "/",
    response_model=DocumentRead,
    summary="Create Document in Local DB (permission aware)"
)
def attach_document(
    payload: DocumentCreate,
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    # Ensure the event exists
    event = session.get(Event, payload.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Associated event not found")

    # Ensure user has permissions for the event's building
    verify_user_building_access(session, current_user, event.building_id)

    document = Document.from_orm(payload)
    session.add(document)
    session.commit()
    session.refresh(document)

    return document


@router.put(
    "/{document_id}",
    response_model=DocumentRead,
    summary="Update Document in Local DB"
)
def update_document_local(
    document_id: int,
    payload: DocumentUpdate,
    session: Session = Depends(get_session)
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    update_data = payload.dict(exclude_unset=True)

    for key, value in update_data.items():
        setattr(document, key, value)

    session.commit()
    session.refresh(document)

    return document


@router.get("/", response_model=List[Document], summary="List Local Documents")
def list_documents(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Document).offset(offset).limit(min(limit, 200))
    ).all()


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.delete("/{document_id}", dependencies=[Depends(get_current_user)])
def delete_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    session.delete(document)
    session.commit()

    return {"message": f"Document {document_id} deleted successfully"}


# -----------------------------------------------------
# INTERNAL FULL SYNC HELPER (Called by sync.py only)
# -----------------------------------------------------

def run_full_document_sync(session: Session):
    """
    Per-module document sync used by:
      - /api/v1/sync/run (manual)
      - daily job scheduler
    """
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        local_docs = session.exec(select(Document)).all()
        local_keys = {d.s3_key for d in local_docs}

        supa_result = client.table("documents").select("*").execute()
        supa_data = supa_result.data or []
        supa_keys = {row["s3_key"] for row in supa_data}

        missing_in_supa = [d for d in local_docs if d.s3_key not in supa_keys]
        missing_in_local = [row for row in supa_data if row["s3_key"] not in local_keys]

        inserted_to_supa, inserted_to_local = [], []

        # Push → Supabase
        for d in missing_in_supa:
            payload = {
                "event_id": d.event_id,
                "s3_key": d.s3_key,
                "filename": d.filename,
                "content_type": d.content_type,
                "size_bytes": d.size_bytes,
                "created_at": d.created_at.isoformat(),
            }
            result = client.table("documents").insert(payload).execute()
            if result.data:
                inserted_to_supa.append(d.s3_key)

        # Pull → Local
        for row in missing_in_local:
            new_doc = Document(
                event_id=row["event_id"],
                s3_key=row["s3_key"],
                filename=row["filename"],
                content_type=row.get("content_type"),
                size_bytes=row.get("size_bytes"),
            )
            session.add(new_doc)
            inserted_to_local.append(row["s3_key"])

        session.commit()

        return {
            "status": "ok",
            "summary": {
                "local_total": len(local_docs),
                "supa_total": len(supa_data),
                "inserted_to_supabase": inserted_to_supa,
                "inserted_to_local": inserted_to_local,
            },
            "message": (
                f"Document sync complete — "
                f"{len(inserted_to_supa)} → Supabase, "
                f"{len(inserted_to_local)} → Local DB."
            ),
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Full document sync failed: {e}")
