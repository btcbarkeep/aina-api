# routers/uploads.py

from fastapi import (
    APIRouter, UploadFile, File, Form,
    Depends, HTTPException
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
# Helper — sanitize dict ("" → None)
# -----------------------------------------------------
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
        else:
            clean[k] = v
    return clean


# -----------------------------------------------------
# Helper — validate & sanitize filename
# -----------------------------------------------------
def safe_filename(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)


# -----------------------------------------------------
# AWS CONFIGURATION
# -----------------------------------------------------
def get_s3_client():
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
    AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME]):
        raise RuntimeError("Missing AWS credentials or bucket name.")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
    return s3, AWS_BUCKET_NAME, AWS_REGION


# -----------------------------------------------------
# Helper — SAFE building access check
# -----------------------------------------------------
def verify_user_building_access(current_user: CurrentUser, building_id: str):

    # Admin, super_admin and manager bypass
    if current_user.role in ["admin", "super_admin", "manager"]:
        return

    client = get_supabase_client()

    result = (
        client.table("user_building_access")
        .select("*")  # The table does NOT have an id column
        .eq("user_id", current_user.id)
        .eq("building_id", building_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(403, "User does not have access to this building.")


# -----------------------------------------------------
# Helper — event_id → building_id (NO .single())
# -----------------------------------------------------
def get_event_building_id(event_id: str | None):
    if not event_id:
        return None

    client = get_supabase_client()

    rows = (
        client.table("events")
        .select("building_id")
        .eq("id", event_id)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(404, "Event not found.")

    return rows[0]["building_id"]


# -----------------------------------------------------
# UPLOAD DOCUMENT (permission: upload:write)
# -----------------------------------------------------
@router.post(
    "/",
    summary="Upload a document file",
    dependencies=[Depends(requires_permission("upload:write"))],
)
async def upload_document(
    file: UploadFile = File(...),
    building_id: str = Form(...),
    event_id: str | None = Form(None),
    category: str | None = Form(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Uploads a document to S3 and creates a Supabase record.
    """

    # -------------------------------------------------
    # Validate event belongs to building (if provided)
    # -------------------------------------------------
    event_building = get_event_building_id(event_id)

    if event_building and event_building != building_id:
        raise HTTPException(400, "Event does not belong to this building.")

    # -------------------------------------------------
    # Building access rules
    # -------------------------------------------------
    verify_user_building_access(current_user, building_id)

    # -------------------------------------------------
    # Prepare S3 upload
    # -------------------------------------------------
    try:
        s3, bucket, region = get_s3_client()

        clean_filename = safe_filename(file.filename)

        safe_category = (
            category.strip().replace(" ", "_").lower()
            if category else "general"
        )

        # Determine S3 key structure
        if event_id:
            s3_key = f"events/{event_id}/documents/{safe_category}/{clean_filename}"
        else:
            s3_key = f"buildings/{building_id}/documents/{safe_category}/{clean_filename}"

        # Upload to S3
        s3.upload_fileobj(
            Fileobj=file.file,
            Bucket=bucket,
            Key=s3_key,
            ExtraArgs={"ContentType": file.content_type},
        )

        # Generate presigned URL (1 day)
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=86400,
        )

        # -------------------------------------------------
        # Create Supabase document record (SAFE 2-STEP)
        # -------------------------------------------------
        payload = sanitize({
            "event_id": event_id,
            "building_id": building_id,
            "s3_key": s3_key,
            "filename": clean_filename,
            "content_type": file.content_type,
            "size_bytes": getattr(file, "size", None),
            "uploaded_by": current_user.id,
        })

        client = get_supabase_client()

        # Step 1 — Insert
        insert_res = (
            client.table("documents")
            .insert(payload)
            .execute()
        )

        if not insert_res.data:
            raise HTTPException(500, "Supabase insert returned no data.")

        doc_id = insert_res.data[0]["id"]

        # Step 2 — Fetch document
        fetch_res = (
            client.table("documents")
            .select("*")
            .eq("id", doc_id)
            .execute()
        )

        if not fetch_res.data:
            raise HTTPException(500, "Created document not found.")

        # -------------------------------------------------
        # Response
        # -------------------------------------------------
        return {
            "upload": {
                "filename": clean_filename,
                "s3_key": s3_key,
                "presigned_url": presigned_url,
                "uploaded_at": datetime.utcnow().isoformat(),
            },
            "document": fetch_res.data[0],
        }

    except (NoCredentialsError, ClientError) as e:
        raise HTTPException(500, f"S3 error: {e}")
