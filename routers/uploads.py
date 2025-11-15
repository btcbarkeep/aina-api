# routers/uploads.py
from fastapi import (
    APIRouter, UploadFile, File, Form,
    Depends, HTTPException
)
from datetime import datetime
import boto3
import os
from botocore.exceptions import ClientError, NoCredentialsError

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client


router = APIRouter(
    prefix="/uploads",
    tags=["Uploads"],
)

"""
UPLOAD ROUTER

Rules:
- Any authenticated user may upload IF they have building access.
- Admin/Manager bypass building access checks.
"""


# -----------------------------------------------------
#  AWS CONFIGURATION
# -----------------------------------------------------
def get_s3_client():
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
    AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME]):
        raise RuntimeError("Missing AWS credentials or bucket name")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
    return s3, AWS_BUCKET_NAME, AWS_REGION


# -----------------------------------------------------
# Helper: Building Access
# -----------------------------------------------------
def verify_user_building_access(user: CurrentUser, building_id: str):
    """Admins & managers bypass. Others must have building access."""
    if user.role in ["admin", "manager"]:
        return

    client = get_supabase_client()
    result = (
        client.table("user_building_access")
        .select("id")
        .eq("user_id", user.user_id)
        .eq("building_id", building_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=403,
            detail="User does not have access to this building."
        )


# -----------------------------------------------------
#  UPLOAD FILE + CREATE DOCUMENT RECORD
# -----------------------------------------------------
@router.post("/", summary="Upload a document file")
async def upload_document(
    file: UploadFile = File(...),
    building_id: str = Form(...),
    event_id: str | None = Form(None),
    category: str | None = Form(None),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Uploads a file to S3 and creates a matching Supabase document record.

    Access:
      - Admin / manager: allowed for any building.
      - Regular users: only if they have building access.
    """
    verify_user_building_access(current_user, building_id)

    try:
        s3, bucket, region = get_s3_client()

        # ------------------------------
        # Build S3 path
        # ------------------------------
        safe_category = (
            category.strip().replace(" ", "_").lower()
            if category else "general"
        )

        if event_id:
            s3_key = f"events/{event_id}/documents/{safe_category}/{file.filename}"
        else:
            s3_key = f"buildings/{building_id}/documents/{safe_category}/{file.filename}"

        # ------------------------------
        # Upload to S3
        # ------------------------------
        s3.upload_fileobj(
            Fileobj=file.file,
            Bucket=bucket,
            Key=s3_key,
            ExtraArgs={"ContentType": file.content_type},
        )

        # ------------------------------
        # Generate presigned URL
        # ------------------------------
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=86400,  # 24 hours
        )

        # ------------------------------
        # Create Supabase document
        # ------------------------------
        payload = {
            "event_id": event_id,
            "building_id": building_id,
            "s3_key": s3_key,
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": file.spool_max_size or None,
            "created_at": datetime.utcnow().isoformat(),
            "uploaded_by": current_user.user_id,
        }

        client = get_supabase_client()
        result = client.table("documents").insert(payload).execute()

        if not result.data:
            raise HTTPException(500, "Failed to insert Supabase document record")

        return {
            "upload": {
                "filename": file.filename,
                "s3_key": s3_key,
                "presigned_url": presigned_url,
                "uploaded_at": datetime.utcnow().isoformat(),
            },
            "document": result.data[0],
        }

    except (NoCredentialsError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))
