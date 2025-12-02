# routers/uploads.py

from fastapi import (
    APIRouter, UploadFile, File, Form,
    Depends, HTTPException, Path
)
from datetime import datetime
import boto3
import os
import re
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

    category: str | None = Form(None),

    # Redaction and visibility toggles
    is_redacted: bool = Form(False, description="Whether the document should be marked as redacted"),
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

    # -----------------------------------------------------
    # Resolve building + unit from ANY provided input
    # -----------------------------------------------------

    # If event is provided → derive building + unit
    event_building, event_unit = get_event_info(event_id)

    # If event provided, but user also supplied inconsistent building/unit
    if event_id:
        if building_id and building_id != event_building:
            raise HTTPException(400, "Event does not belong to building.")
        building_id = event_building

        if unit_id is None:
            unit_id = event_unit  # inherit unit from event
        elif event_unit and unit_id != event_unit:
            raise HTTPException(400, "Event + unit mismatch.")

    # If unit provided → derive building
    if unit_id:
        unit_building = get_unit_building(unit_id)
        if building_id and building_id != unit_building:
            raise HTTPException(400, "Unit does not belong to building.")
        building_id = unit_building

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

    # Upload file
    try:
        s3.upload_fileobj(
            Fileobj=file.file,
            Bucket=bucket,
            Key=s3_key,
            ExtraArgs={"ContentType": file.content_type},
        )
    except Exception as e:
        raise HTTPException(500, f"S3 upload error: {e}")

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
        "unit_id": unit_id,
        "category": category,
        "filename": clean_filename,
        "s3_key": s3_key,
        "content_type": file.content_type,
        "uploaded_by": current_user.id,
        "is_redacted": is_redacted,
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

    # Step 2 — Fetch
    fetch_res = (
        client.table("documents")
        .select("*")
        .eq("id", doc_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Created document not found")

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
        "document": fetch_res.data[0],
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

