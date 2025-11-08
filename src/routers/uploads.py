from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query
import boto3
import os
from datetime import datetime
from botocore.exceptions import NoCredentialsError, ClientError
from src.dependencies import get_active_user, get_admin_user

router = APIRouter(prefix="/upload", tags=["Uploads"])

# -----------------------------------------------------
#  AWS CONFIGURATION
# -----------------------------------------------------
def get_s3_client():
    """Initialize and return an authenticated S3 client."""
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
#  UPLOAD FILE (Protected)
# -----------------------------------------------------
@router.post("/", dependencies=[Depends(get_active_user)])
async def upload_file(
    file: UploadFile = File(...),
    complex_name: str = Form(...),
    category: str = Form(...),
    scope: str = Form("complex"),
    unit_name: str | None = Form(None)
):
    """
    Upload a file to S3 (private) and return a presigned download URL.
    """
    try:
        s3, bucket, region = get_s3_client()

        # sanitize naming
        safe_complex = complex_name.strip().replace(" ", "_").upper()
        safe_category = category.strip().replace(" ", "_").lower()

        if scope == "unit":
            if not unit_name:
                raise HTTPException(status_code=400, detail="unit_name required when scope='unit'")
            safe_unit = unit_name.strip().replace(" ", "_").upper()
            key = f"complexes/{safe_complex}/units/{safe_unit}/{safe_category}/{file.filename}"
        else:
            key = f"complexes/{safe_complex}/complex/{safe_category}/{file.filename}"

        # Upload (private)
        s3.upload_fileobj(
            Fileobj=file.file,
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": file.content_type},
        )

        # Generate presigned URL (valid 24 hours)
        presigned_url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=86400,
        )

        return {
            "filename": file.filename,
            "s3_key": key,
            "presigned_url": presigned_url,
            "scope": scope,
            "complex": safe_complex,
            "category": safe_category,
            "uploaded_at": datetime.utcnow().isoformat(),
        }

    except (NoCredentialsError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------
#  LIST FILES BY COMPLEX / CATEGORY (Protected)
# -----------------------------------------------------
@router.get("/", dependencies=[Depends(get_active_user)])
def list_files(
    complex_name: str = Query(..., description="Complex name (e.g., 'KAHANA_VILLA')"),
    unit_name: str | None = Query(None, description="Unit name if scope=unit"),
    category: str | None = Query(None, description="Category filter (e.g., 'permits', 'reports')"),
    expires_in: int = Query(86400, ge=60, le=604800, description="Presigned URL expiration time in seconds (default 24h)"),
):
    """
    List uploaded files for a complex, optionally filtered by unit or category.
    Returns file metadata + presigned URLs.
    """
    try:
        s3, bucket, _ = get_s3_client()

        safe_complex = complex_name.strip().replace(" ", "_").upper()
        prefix = f"complexes/{safe_complex}/"

        if unit_name:
            safe_unit = unit_name.strip().replace(" ", "_").upper()
            prefix += f"units/{safe_unit}/"
        else:
            prefix += "complex/"

        if category:
            prefix += f"{category.strip().replace(' ', '_').lower()}/"

        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        files = []

        if "Contents" not in response:
            return {"files": [], "message": "No files found"}

        for obj in response["Contents"]:
            key = obj["Key"]
            filename = key.split("/")[-1]
            last_modified = obj.get("LastModified")
            size_kb = round(obj.get("Size", 0) / 1024, 2)

            presigned_url = s3.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )

            files.append({
                "filename": filename,
                "s3_key": key,
                "size_kb": size_kb,
                "last_modified": last_modified.isoformat() if last_modified else None,
                "presigned_url": presigned_url
            })

        return {
            "complex": safe_complex,
            "category": category or "all",
            "file_count": len(files),
            "files": sorted(files, key=lambda x: x["filename"]),
        }

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")


# -----------------------------------------------------
#  LIST ALL FILES (Admin-only)
# -----------------------------------------------------
@router.get("/all")
def list_all_files(
    expires_in: int = Query(
        86400,
        ge=60,
        le=604800,
        description="Presigned URL expiration time in seconds (default 24h)",
    ),
    current_admin: dict = Depends(get_admin_user),  # 👈 THIS enforces admin
):
    """
    Admin-only endpoint to list *all* files in the S3 bucket.
    """
    try:
        s3, bucket, _ = get_s3_client()
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket)
        all_files = []

        for page in pages:
            if "Contents" not in page:
                continue
            for obj in page["Contents"]:
                key = obj["Key"]
                filename = key.split("/")[-1]
                last_modified = obj.get("LastModified")
                size_kb = round(obj.get("Size", 0) / 1024, 2)

                presigned_url = s3.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": bucket, "Key": key},
                    ExpiresIn=expires_in,
                )

                all_files.append({
                    "filename": filename,
                    "s3_key": key,
                    "size_kb": size_kb,
                    "last_modified": last_modified.isoformat() if last_modified else None,
                    "presigned_url": presigned_url
                })

        return {
            "total_files": len(all_files),
            "files": sorted(all_files, key=lambda x: x["s3_key"]),
        }

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error listing all files: {str(e)}")


# -----------------------------------------------------
#  DELETE FILE (Protected)
# -----------------------------------------------------
@router.delete("/", dependencies=[Depends(get_active_user)])
def delete_file(
    s3_key: str = Query(..., description="Full S3 object key to delete, e.g. 'complexes/KAHANA_VILLA/complex/permits/file.pdf'")
):
    """
    Delete a file from the S3 bucket using its key.
    Only authenticated users can delete files.
    """
    try:
        s3, bucket, _ = get_s3_client()
        s3.delete_object(Bucket=bucket, Key=s3_key)
        return {"message": f"✅ File '{s3_key}' deleted successfully"}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")
