# routers/uploads.py

from fastapi import (
    APIRouter, UploadFile, File, Form,
    Depends, HTTPException, Path
)
from datetime import datetime
import boto3
import os
import re
import tempfile
from pathlib import Path as PathLib
from botocore.exceptions import ClientError, NoCredentialsError

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client

router = APIRouter(
    prefix="/uploads",
    tags=["Uploads"],
)

# -----------------------------------------------------
# Sanitize helper
# -----------------------------------------------------
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if v is None:
            clean[k] = None
        elif isinstance(v, bool):
            clean[k] = v  # Preserve boolean values
        elif isinstance(v, str):
            clean[k] = v.strip() or None
        else:
            clean[k] = str(v)
    return clean

# -----------------------------------------------------
# Filename sanitizer
# -----------------------------------------------------
def safe_filename(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)

# -----------------------------------------------------
# Normalize swagger-like values
# -----------------------------------------------------
def normalize_uuid_like(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if not v or v.lower() in {"string", "null", "undefined"}:
        return None
    return v

# -----------------------------------------------------
# AWS S3
# -----------------------------------------------------
def get_s3():
    key = os.getenv("AWS_ACCESS_KEY_ID")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    bucket = os.getenv("AWS_BUCKET_NAME")
    region = os.getenv("AWS_REGION", "us-east-2")

    if not all([key, secret, bucket]):
        raise RuntimeError("Missing AWS credentials")

    client = boto3.client(
        "s3",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name=region,
    )

    return client, bucket, region

# -----------------------------------------------------
# Building access check
# -----------------------------------------------------
def verify_user_building_access(current_user: CurrentUser, building_id: str):
    if current_user.role in ["admin", "super_admin", "hoa"]:
        return

    client = get_supabase_client()
    rows = (
        client.table("user_building_access")
        .select("*")
        .eq("user_id", current_user.id)
        .eq("building_id", building_id)
        .execute()
    ).data

    if not rows:
        raise HTTPException(403, "User does not have access to this building.")

# -----------------------------------------------------
# event_id → (building_id, unit_id)
# -----------------------------------------------------
def get_event_info(event_id: str | None):
    normalized = normalize_uuid_like(event_id)
    if not normalized:
        return None, None

    client = get_supabase_client()
    rows = (
        client.table("events")
        .select("building_id, unit_id")
        .eq("id", normalized)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(404, "Event not found")

    return rows[0]["building_id"], rows[0].get("unit_id")

# -----------------------------------------------------
# unit_id → building_id
# -----------------------------------------------------
def get_unit_building(unit_id: str | None):
    normalized = normalize_uuid_like(unit_id)
    if not normalized:
        return None

    client = get_supabase_client()
    rows = (
        client.table("units")
        .select("building_id")
        .eq("id", normalized)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(400, "Unit not found")

    return rows[0]["building_id"]

# -----------------------------------------------------
# UPLOAD DOCUMENT — NOW UNIT-AWARE
# -----------------------------------------------------
@router.post(
    "/",
    summary="Upload a document and create a document record",
    dependencies=[Depends(requires_permission("upload:write"))],
)
async def upload_document(
    file: UploadFile = File(...),

    # Required filename
    filename: str = Form(...),

    # New full compatibility
    building_id: str | None = Form(None),
    event_id: str | None = Form(None),
    unit_id: str | None = Form(None),
    
    # NEW — Multiple units and contractors support
    unit_ids: str | None = Form(None, description="JSON array of unit IDs: [\"uuid1\", \"uuid2\"]"),
    contractor_ids: str | None = Form(None, description="JSON array of contractor IDs: [\"uuid1\", \"uuid2\"]"),

    category: str | None = Form(None),

    # Visibility toggle (redaction is now manual via separate endpoint)
    is_public: bool = Form(False, description="Whether the document should be public (false = private)"),

    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Uploads a file to S3 AND creates a Supabase document record.
    Supports: building_id, event_id, unit_id.
    Requires: filename (custom filename for the uploaded file).
    """

    # Normalize values
    building_id = normalize_uuid_like(building_id)
    event_id = normalize_uuid_like(event_id)
    unit_id = normalize_uuid_like(unit_id)
    
    # Parse unit_ids and contractor_ids from JSON strings
    parsed_unit_ids = []
    if unit_ids:
        try:
            import json
            parsed_unit_ids = json.loads(unit_ids)
            if not isinstance(parsed_unit_ids, list):
                parsed_unit_ids = []
        except Exception:
            parsed_unit_ids = []
    
    parsed_contractor_ids = []
    if contractor_ids:
        try:
            import json
            parsed_contractor_ids = json.loads(contractor_ids)
            if not isinstance(parsed_contractor_ids, list):
                parsed_contractor_ids = []
        except Exception:
            parsed_contractor_ids = []
    
    # Combine unit_id (legacy) with unit_ids (new)
    if unit_id and unit_id not in parsed_unit_ids:
        parsed_unit_ids.insert(0, unit_id)
    elif not parsed_unit_ids and unit_id:
        parsed_unit_ids = [unit_id]

    # -----------------------------------------------------
    # Resolve building + unit from ANY provided input
    # -----------------------------------------------------

    # If event is provided → derive building + unit
    if event_id:
        event_building, event_unit = get_event_info(event_id)
        
        if building_id and building_id != event_building:
            raise HTTPException(400, "Event does not belong to building.")
        building_id = event_building

        # Add event's unit to unit_ids if not already present
        if event_unit and event_unit not in parsed_unit_ids:
            parsed_unit_ids.append(event_unit)

    # If units provided → derive building from first unit and validate all belong to same building
    if parsed_unit_ids:
        unit_building = get_unit_building(parsed_unit_ids[0])
        if building_id and building_id != unit_building:
            raise HTTPException(400, "Unit does not belong to building.")
        building_id = unit_building
        
        # Validate all units belong to same building
        for uid in parsed_unit_ids[1:]:
            uid_building = get_unit_building(uid)
            if uid_building != building_id:
                raise HTTPException(400, f"All units must belong to the same building. Unit {uid} belongs to {uid_building}, expected {building_id}.")
    
    # Set legacy unit_id for backward compatibility (first unit if any)
    unit_id = parsed_unit_ids[0] if parsed_unit_ids else None

    # If building not provided → error
    if not building_id:
        raise HTTPException(400, "Must provide either event_id, unit_id, or building_id.")

    # -----------------------------------------------------
    # Permission check
    # -----------------------------------------------------
    verify_user_building_access(current_user, building_id)

    # -----------------------------------------------------
    # Prepare S3 key
    # -----------------------------------------------------
    s3, bucket, region = get_s3()

    # Use the provided filename (required), sanitize it
    if not filename or not filename.strip():
        raise HTTPException(400, "filename is required and cannot be empty")
    clean_filename = safe_filename(filename.strip())

    safe_category = (
        category.strip().replace(" ", "_").lower()
        if category else "general"
    )

    # NEW S3 path rules
    if event_id:
        s3_key = f"events/{event_id}/units/{unit_id or 'none'}/documents/{safe_category}/{clean_filename}"

    elif unit_id:
        s3_key = f"units/{unit_id}/documents/{safe_category}/{clean_filename}"

    else:
        s3_key = f"buildings/{building_id}/documents/{safe_category}/{clean_filename}"

    # -----------------------------------------------------
    # Save file temporarily and upload to S3
    # -----------------------------------------------------
    temp_file_path = None

    try:
        # Save uploaded file to temporary location
        file_extension = PathLib(file.filename or clean_filename).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file_path = temp_file.name
            # Read and write the file content
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()

        # Upload file to S3
        try:
            s3.upload_file(
                Filename=temp_file_path,
                Bucket=bucket,
                Key=s3_key,
                ExtraArgs={"ContentType": file.content_type},
            )
        except Exception as e:
            raise HTTPException(500, f"S3 upload error: {e}")
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                print(f"Warning: Failed to delete temp file {temp_file_path}: {e}")

    # Generate presigned URL for immediate use (expires in 1 day)
    # Note: For long-term access, use the /documents/{id}/download endpoint
    presigned_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=86400,  # 1 day
    )

    # -----------------------------------------------------
    # Create document record
    # -----------------------------------------------------
    client = get_supabase_client()

    payload = sanitize({
        "building_id": building_id,
        "event_id": event_id,
        "unit_id": unit_id,  # Legacy field (first unit for backward compatibility)
        "category": category,
        "filename": clean_filename,
        "s3_key": s3_key,
        "content_type": file.content_type,
        "uploaded_by": current_user.id,
        "is_redacted": False,  # Manual redaction is handled via separate endpoint
        "is_public": is_public,
        # Note: Don't store download_url - it expires. Use /documents/{id}/download endpoint instead
    })

    # Step 1 — Insert
    insert_res = (
        client.table("documents")
        .insert(payload)
        .execute()
    )

    if not insert_res.data:
        raise HTTPException(500, "Insert returned no data")

    doc_id = insert_res.data[0]["id"]

    # Step 2 — Create junction table entries for units
    if parsed_unit_ids:
        for unit_id_val in parsed_unit_ids:
            try:
                client.table("document_units").insert({
                    "document_id": doc_id,
                    "unit_id": unit_id_val
                }).execute()
            except Exception as e:
                # Ignore duplicate key errors (unique constraint)
                if "duplicate" not in str(e).lower():
                    print(f"Warning: Failed to create document_unit relationship: {e}")
    
    # Step 3 — Create junction table entries for contractors
    if parsed_contractor_ids:
        for contractor_id_val in parsed_contractor_ids:
            try:
                client.table("document_contractors").insert({
                    "document_id": doc_id,
                    "contractor_id": contractor_id_val
                }).execute()
            except Exception as e:
                # Ignore duplicate key errors (unique constraint)
                if "duplicate" not in str(e).lower():
                    print(f"Warning: Failed to create document_contractor relationship: {e}")

    # Step 4 — Fetch with relations
    fetch_res = (
        client.table("documents")
        .select("*")
        .eq("id", doc_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Created document not found")
    
    document = fetch_res.data[0]
    
    # Enrich with units and contractors
    # Fetch units and contractors from junction tables
    document_units = (
        client.table("document_units")
        .select("unit_id, units(*)")
        .eq("document_id", doc_id)
        .execute()
    )
    units = []
    if document_units.data:
        for row in document_units.data:
            if row.get("units"):
                units.append(row["units"])
    
    document_contractors = (
        client.table("document_contractors")
        .select("contractor_id, contractors(*)")
        .eq("document_id", doc_id)
        .execute()
    )
    contractors = []
    if document_contractors.data:
        for row in document_contractors.data:
            if row.get("contractors"):
                contractors.append(row["contractors"])
    
    document["units"] = units
    document["contractors"] = contractors
    document["unit_ids"] = [u["id"] for u in units]
    document["contractor_ids"] = [c["id"] for c in contractors]

    # -----------------------------------------------------
    # Update event with s3_key if event_id is provided
    # -----------------------------------------------------
    if event_id:
        try:
            client.table("events").update({
                "s3_key": s3_key
            }).eq("id", event_id).execute()
        except Exception as e:
            # Log error but don't fail the upload
            print(f"Warning: Failed to update event {event_id} with s3_key: {e}")

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------
    return {
        "upload": {
            "filename": clean_filename,
            "s3_key": s3_key,
            "presigned_url": presigned_url,  # Valid for 1 day
            "uploaded_at": datetime.utcnow().isoformat(),
        },
        "document": document,
    }


# -----------------------------------------------------
# GET PRESIGNED URL FOR DOCUMENT (on-demand) - PUBLIC
# -----------------------------------------------------
@router.get(
    "/documents/{document_id}/download",
    summary="Get a presigned URL for downloading a document (public)",
)
async def get_document_download_url(
    document_id: str = Path(..., description="Document ID"),
):
    """
    Generates a fresh presigned URL for a document.
    Public endpoint - no authentication required.
    Use this endpoint when download_url has expired or doesn't exist.
    """
    client = get_supabase_client()

    # Fetch document
    rows = (
        client.table("documents")
        .select("s3_key")
        .eq("id", document_id)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(404, "Document not found")

    doc = rows[0]

    if not doc.get("s3_key"):
        raise HTTPException(400, "Document has no S3 key")

    # Generate presigned URL
    s3, bucket, region = get_s3()

    try:
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": doc["s3_key"]},
            ExpiresIn=3600,  # 1 hour
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to generate presigned URL: {e}")

    return {
        "document_id": document_id,
        "download_url": presigned_url,
        "expires_in": 3600,
    }

