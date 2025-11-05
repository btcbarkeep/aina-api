from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
import boto3
import os
from datetime import datetime
from botocore.exceptions import NoCredentialsError, ClientError

router = APIRouter()


# -----------------------------------------------------
#  AWS CONFIGURATION
# -----------------------------------------------------
def get_s3_client():
    """
    Initializes and returns an authenticated S3 client.
    Requires AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_BUCKET_NAME
    to be defined in Render environment variables.
    """
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
    AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME]):
        raise RuntimeError("Missing AWS S3 credentials or bucket name in environment variables.")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
    return s3, AWS_BUCKET_NAME, AWS_REGION


# -----------------------------------------------------
#  UPLOAD FILE
# -----------------------------------------------------
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    complex_name: str = Form(...),
    category: str = Form(...),
    scope: str = Form("complex"),        # "complex" or "unit"
    unit_name: str | None = Form(None)   # only required when scope == "unit"
):
    """
    Uploads a file to S3 in the correct hierarchy.

    Structure:
        complexes/{complex_name}/complex/{category}/{filename}
        complexes/{complex_name}/units/{unit_name}/{category}/{filename}
    """
    try:
        s3, bucket, region = get_s3_client()

        # --- Normalize inputs ---
        safe_complex = complex_name.strip().replace(" ", "_").upper()
        safe_category = category.strip().replace(" ", "_").lower()

        if scope == "unit":
            if not unit_name:
                raise HTTPException(status_code=400, detail="unit_name is required when scope='unit'")
            safe_unit = unit_name.strip().replace(" ", "_").upper()
            key = f"complexes/{safe_complex}/units/{safe_unit}/{safe_category}/{file.filename}"
        else:
            key = f"complexes/{safe_complex}/complex/{safe_category}/{file.filename}"

        # --- Upload to S3 ---
        s3.upload_fileobj(
            Fileobj=file.file,
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": file.content_type},
        )

        # --- Build download URL ---
        download_url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

        return {
            "filename": file.filename,
            "scope": scope,
            "complex": safe_complex,
            "unit": safe_unit if scope == "unit" else None,
            "category": safe_category,
            "path": key,
            "content_type": file.content_type,
            "uploaded_at": datetime.utcnow().isoformat(),
            "download_url": download_url,
        }

    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="AWS credentials not found.")
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error uploading to S3: {e}")


# -----------------------------------------------------
#  LIST FILES
# -----------------------------------------------------
from datetime import datetime
from fastapi import Query, HTTPException
from botocore.exceptions import ClientError


@router.get("/files")
def list_files(
    complex_name: str = Query(..., description="Name of the complex (e.g. Kahana Villa)"),
    scope: str = Query("complex", description="Scope: 'complex' or 'unit'"),
    unit_name: str | None = Query(None, description="Required if scope='unit'"),
    category: str | None = Query(None, description="Optional folder/category filter"),
    limit: int = Query(50, ge=1, le=200, description="Max number of results to return"),
    offset: int = Query(0, ge=0, description="Results offset for pagination"),
    uploaded_after: str | None = Query(None, description="Filter by date (ISO format, e.g. 2025-10-01)"),
    uploaded_before: str | None = Query(None, description="Filter by date (ISO format, e.g. 2025-11-01)")
):
    """
    Lists files from S3 for a specific complex or unit.
    Supports optional filtering by category, date, and pagination.

    Examples:
        /files?complex_name=Kahana%20Villa&scope=complex
        /files?complex_name=Kahana%20Villa&scope=unit&unit_name=302&category=insurance
        /files?complex_name=Kahana%20Villa&limit=20&offset=0&uploaded_after=2025-10-01
    """

    try:
        s3, bucket, region = get_s3_client()

        # --- Sanitize inputs ---
        safe_complex = complex_name.strip().replace(" ", "_").upper()

        if scope == "unit":
            if not unit_name:
                raise HTTPException(status_code=400, detail="unit_name is required when scope='unit'")
            safe_unit = unit_name.strip().replace(" ", "_").upper()
            prefix = f"complexes/{safe_complex}/units/{safe_unit}/"
        else:
            prefix = f"complexes/{safe_complex}/complex/"

        if category:
            safe_category = category.strip().replace(" ", "_").lower()
            prefix += f"{safe_category}/"

        # --- Query S3 ---
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)

        if "Contents" not in response:
            return {"files": [], "message": "No files found."}

        files = []
        for obj in response["Contents"]:
            key = obj["Key"]
            if key.endswith("/"):  # skip folders
                continue

            file_date = obj["LastModified"]
            if uploaded_after or uploaded_before:
                after = datetime.fromisoformat(uploaded_after) if uploaded_after else None
                before = datetime.fromisoformat(uploaded_before) if uploaded_before else None
                if after and file_date < after:
                    continue
                if before and file_date > before:
                    continue

            files.append({
                "filename": key.split("/")[-1],
                "key": key,
                "size_kb": round(obj["Size"] / 1024, 2),
                "last_modified": file_date.isoformat(),
                "download_url": f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
            })

        # --- Sort newest first ---
        files.sort(key=lambda x: x["last_modified"], reverse=True)

        # --- Apply pagination ---
        paged_files = files[offset:offset + limit]

        return {
            "complex": safe_complex,
            "scope": scope,
            "unit": safe_unit if scope == "unit" else None,
            "category": category,
            "count_total": len(files),
            "count_returned": len(paged_files),
            "limit": limit,
            "offset": offset,
            "files": paged_files
        }

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error listing S3 files: {e}")

from fastapi import Path


from routers.auth import get_current_user

@router.delete("/files/{key:path}")
def delete_file(
    key: str,
    force: bool = Query(False),
    user=Depends(get_current_user)
):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to delete files")

    try:
        s3, bucket, _ = get_s3_client()
        if not force:
            try:
                s3.head_object(Bucket=bucket, Key=key)
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    raise HTTPException(status_code=404, detail=f"File not found: {key}")
                raise
        s3.delete_object(Bucket=bucket, Key=key)
        return {"deleted": True, "key": key, "message": "File successfully deleted from S3"}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {e}")
