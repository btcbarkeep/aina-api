# routers/documents.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
import traceback

from database import get_session
from dependencies.auth import get_current_user
from models import Document, DocumentCreate, DocumentRead, DocumentUpdate

from core.supabase_client import get_supabase_client
from core.auth_helpers import verify_user_building_access
from models import Event  # needed to check which building the document’s event belongs to


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


"""
Documents sync with Supabase handles file metadata (event attachments, HOA files, etc.).
Actual files live in S3 or Supabase storage; metadata is mirrored here.
"""


# =====================================================
# 🟢 SUPABASE INTEGRATION
# =====================================================
@router.get("/supabase", summary="List Documents (Supabase)")
def list_documents_supabase(limit: int = 50):
    """Fetch documents directly from Supabase for verification/debugging."""
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        result = client.table("documents").select("*").limit(limit).execute()
        return result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")


@router.post("/supabase", response_model=DocumentRead, summary="Create Document (Supabase + Permissions)")
def create_document_supabase(
    payload: DocumentCreate,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    """Insert a new document record into Supabase with building access enforcement."""
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # ✅ Verify the event and its building
    event = session.get(Event, payload.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Associated event not found")

    verify_user_building_access(session, current_user, event.building_id)

    try:
        result = client.table("documents").upsert(payload.dict(), on_conflict="id").execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Insert failed")
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")

@router.put("/supabase/{document_id}", tags=["Documents"])
def update_document_supabase(document_id: str, payload: DocumentUpdate):
    """
    Update a document record in Supabase by ID.
    """
    update_data = payload.dict(exclude_unset=True)

    result = update_record("documents", document_id, update_data)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]


# =====================================================
# 🧱 LOCAL DOCUMENT CREATION (Protected + Permission Aware)
# =====================================================
@router.post("/", response_model=DocumentRead, summary="Attach Document (Local DB + Permissions)")
def attach_document(
    payload: DocumentCreate,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    """
    Upload or attach a new AOAO document (protected).
    Enforces event + building-level permission using the event’s building_id.
    """
    # ✅ 1. Ensure event exists
    event = session.get(Event, payload.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Associated event not found")

    # ✅ 2. Enforce permission check
    verify_user_building_access(session, current_user, event.building_id)

    # ✅ 3. Create document record
    document = Document.from_orm(payload)
    session.add(document)
    session.commit()
    session.refresh(document)
    return document

@router.put("/{document_id}", response_model=DocumentRead, summary="Update Document (Local DB)")
def update_document_local(
    document_id: int,
    payload: DocumentUpdate,
    session: Session = Depends(get_session),
):
    """
    Update a document record in the local database.
    """
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    update_data = payload.dict(exclude_unset=True)

    for key, value in update_data.items():
        setattr(document, key, value)

    session.add(document)
    session.commit()
    session.refresh(document)

    return document


# =====================================================
# 🧩 SYNC HELPERS
# =====================================================
@router.get("/sync", summary="Compare Local vs Supabase Documents")
def compare_document_sync(session: Session = Depends(get_session)):
    """Compare local and Supabase document tables for differences."""
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        local_docs = session.exec(select(Document)).all()
        local_keys = {d.s3_key for d in local_docs}

        supa_result = client.table("documents").select("s3_key").execute()
        supa_keys = {row["s3_key"] for row in supa_result.data or []}

        local_only = sorted(list(local_keys - supa_keys))
        supabase_only = sorted(list(supa_keys - local_keys))

        return {
            "status": "ok",
            "summary": {
                "local_count": len(local_keys),
                "supabase_count": len(supa_keys),
                "local_only_count": len(local_only),
                "supabase_only_count": len(supabase_only),
            },
            "local_only": local_only,
            "supabase_only": supabase_only,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync comparison failed: {e}")


@router.post("/sync/fix", summary="Push Missing Documents → Supabase")
def fix_document_sync(session: Session = Depends(get_session)):
    """Upload missing local document metadata to Supabase."""
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        local_docs = session.exec(select(Document)).all()
        local_keys = {d.s3_key for d in local_docs}

        supa_result = client.table("documents").select("s3_key").execute()
        supa_keys = {row["s3_key"] for row in supa_result.data or []}

        missing = [d for d in local_docs if d.s3_key not in supa_keys]
        inserted = []

        for d in missing:
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
                inserted.append(d.s3_key)

        return {
            "status": "ok",
            "message": f"Inserted {len(inserted)} missing documents to Supabase.",
            "inserted": inserted,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-sync failed: {e}")


@router.post("/sync/reverse", summary="Pull Missing Documents → Local DB")
def reverse_document_sync(session: Session = Depends(get_session)):
    """Import missing document metadata from Supabase into local DB."""
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        local_docs = session.exec(select(Document)).all()
        local_keys = {d.s3_key for d in local_docs}

        supa_result = client.table("documents").select("*").execute()
        supa_data = supa_result.data or []
        supa_keys = {row["s3_key"] for row in supa_data}

        missing = [row for row in supa_data if row["s3_key"] not in local_keys]
        added = []

        for row in missing:
            new_doc = Document(
                event_id=row.get("event_id"),
                s3_key=row.get("s3_key"),
                filename=row.get("filename"),
                content_type=row.get("content_type"),
                size_bytes=row.get("size_bytes"),
            )
            session.add(new_doc)
            added.append(row.get("s3_key"))

        session.commit()

        return {
            "status": "ok",
            "message": f"Inserted {len(added)} documents from Supabase into local DB.",
            "inserted": added,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reverse sync failed: {e}")


# =====================================================
# 🧠 MASTER SYNC FUNCTION (for Scheduler)
# =====================================================
def run_full_document_sync(session: Session):
    """Synchronize all documents between local DB and Supabase."""
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

        # Push missing → Supabase
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

        # Pull missing → Local
        for row in missing_in_local:
            new_doc = Document(
                event_id=row.get("event_id"),
                s3_key=row.get("s3_key"),
                filename=row.get("filename"),
                content_type=row.get("content_type"),
                size_bytes=row.get("size_bytes"),
            )
            session.add(new_doc)
            inserted_to_local.append(row.get("s3_key"))

        session.commit()

        return {
            "status": "ok",
            "summary": {
                "local_total": len(local_docs),
                "supa_total": len(supa_data),
                "inserted_to_supabase": inserted_to_supa,
                "inserted_to_local": inserted_to_local,
            },
            "message": f"Sync complete — {len(inserted_to_supa)} → Supabase, {len(inserted_to_local)} → Local DB.",
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Full document sync failed: {e}")


@router.post("/sync/full", summary="Full Document Sync")
def full_document_sync(session: Session = Depends(get_session)):
    """API route version of the full document sync."""
    return run_full_document_sync(session)
