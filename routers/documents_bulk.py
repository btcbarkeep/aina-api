# routers/documents_bulk.py

import uuid
import tempfile
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


# ----------------------------------------
# Helper — sanitize dict
# ----------------------------------------
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if v is None:
            clean[k] = None
        elif isinstance(v, str):
            clean[k] = v.strip() or None
        else:
            clean[k] = v
    return clean


# ----------------------------------------
# BULK UPLOAD ENDPOINT
# ----------------------------------------
@router.post(
    "/bulk-upload",
    summary="Bulk upload multiple documents via Excel/PDF list",
    dependencies=[Depends(requires_permission("documents:write"))],
)
async def bulk_upload_documents(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Accepts an Excel file (.xlsx) or CSV containing document metadata.
    Creates 1 row in `documents` per row in the spreadsheet.
    """

    # ------------------------------
    # Validate extension
    # ------------------------------
    filename = file.filename.lower()
    if not (filename.endswith(".xlsx") or filename.endswith(".csv")):
        raise HTTPException(400, "File must be .xlsx or .csv")

    # ------------------------------
    # Read file into pandas
    # ------------------------------
    try:
        contents = await file.read()
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(contents)
            tmp.flush()

            if filename.endswith(".xlsx"):
                df = pd.read_excel(tmp.name)
            else:
                df = pd.read_csv(tmp.name)

    except Exception as e:
        raise HTTPException(400, f"Failed to read spreadsheet: {e}")

    if df.empty:
        raise HTTPException(400, "Spreadsheet is empty.")

    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    required_columns = {"title", "document_url", "building_id"}
    missing = required_columns - set(df.columns)

    if missing:
        raise HTTPException(400, f"Missing required columns: {', '.join(missing)}")

    client = get_supabase_client()

    created_docs = []

    # ------------------------------
    # Loop through all rows and insert
    # ------------------------------
    for _, row in df.iterrows():
        row = row.to_dict()

        doc_data = {
            "id": str(uuid.uuid4()),
            "title": row.get("title"),
            "document_url": row.get("document_url"),
            "building_id": str(row.get("building_id")),
            "unit_id": str(row["unit_id"]) if row.get("unit_id") else None,
            "event_id": str(row["event_id"]) if row.get("event_id") else None,
            "category": row.get("category"),
            "permit_number": row.get("permit_number"),
            "permit_type": row.get("permit_type"),
            "folder": row.get("folder"),
            "tmk": row.get("tmk"),
            "description": row.get("description"),
            "uploaded_by": str(current_user.id),
        }

        sanitized = sanitize(doc_data)

        try:
            res = client.table("documents").insert(sanitized).execute()
        except Exception as e:
            raise HTTPException(500, f"Insert failed: {e}")

        created_docs.append(res.data[0])

    return {
        "status": "success",
        "count": len(created_docs),
        "documents": created_docs,
    }
