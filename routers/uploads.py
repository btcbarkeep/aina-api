# routers/uploads.py
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query
from datetime import datetime
import boto3, os
from botocore.exceptions import ClientError, NoCredentialsError

from dependencies.auth import get_current_user, requires_role

router = APIRouter(prefix="/uploads", tags=["Uploads"])


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
@router.post("/", dependencies=[Depends(get_current_user)])  # ✅ updated
async def upload_file(
    file: UploadFile = File(...),
    complex_name: str = Form(...),
    category: str = Form(...),
    scope: str = Form("complex"),
    unit_name: str | None = Form(None)
):
    """Upload a file to S3 (private) and return a presigned download URL."""
    try:
        s3, bucket, region = get_s3_client()

        safe_complex = complex_name.strip().replace(" ", "_").upper()
        safe_category = category.strip().replace(" ", "_").lower()

        if scope == "unit":
            if not unit_name:
                raise HTTPException(status_code=400, detail="unit_name required when scope='unit'")
            safe_unit = unit_name.strip().replace(" ", "_").upper()
            key = f"complexes/{safe_complex}/units/{safe_unit}/{safe_category}/{file.filename}"
        else:
            key = f"complexes/{safe_complex}/complex/{safe_category}/{file.filename}"

        s3.upload_fileobj(
            Fileobj=file.file,
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": file.content_type},
        )

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
@router.get("/", dependencies=[Depends(get_current_user)])  # ✅ updated
def list_files(
    complex_name: str = Query(...),
    unit_name: str | None = Query(None),
    category: str | None = Query(None),
    expires_in: int = Query(86400, ge=60, le=604800)
):
    """List uploaded files for a complex, optionally filtered by unit or category."""
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
@router.get("/all", dependencies=[Depends(requires_role("admin"))])  # ✅ updated
def list_all_files(
    expires_in: int = Query(86400, ge=60, le=604800),
):
    """Admin-only endpoint to list *all* files in the S3 bucket."""
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
@router.delete("/", dependencies=[Depends(get_current_user)])  # ✅ updated
def delete_file(
    s3_key: str = Query(...)
):
    """Delete a file from the S3 bucket using its key."""
    try:
        s3, bucket, _ = get_s3_client()
        s3.delete_object(Bucket=bucket, Key=s3_key)
        return {"message": f"✅ File '{s3_key}' deleted successfully"}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")
