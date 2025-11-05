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
@router.get("/files")
def list_files(
    complex_name: str = Query(...),
    scope: str = Query("complex"),        # "complex" or "unit"
    unit_name: str | None = Query(None),  # required if scope == "unit"
    category: str | None = Query(None)    # optional filter (e.g. "insurance")
):
    """
    Lists all files in S3 for a given complex or unit.

    Example paths:
        complexes/{complex_name}/complex/{category}/
        complexes/{complex_name}/units/{unit_name}/{category}/
    """
    try:
        s3, bucket, region = get_s3_client()

        safe_complex = complex_name.strip().replace(" ", "_").upper()

        # Determine prefix
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

        # --- Query S3 objects ---
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)

        if "Contents" not in response:
            return {"files": [], "message": "No files found."}

        files = []

        for obj in response["Contents"]:
            key = obj["Key"]
            if key.endswith("/"):  # skip folder placeholders
                continue

            files.append({
                "filename": key.split("/")[-1],
                "key": key,
                "size_kb": round(obj["Size"] / 1024, 2),
                "last_modified": obj["LastModified"].isoformat(),
                "download_url": f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
            })

        return {
            "complex": safe_complex,
            "scope": scope,
            "unit": safe_unit if scope == "unit" else None,
            "category": category,
            "count": len(files),
            "files": files
        }

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error listing S3 files: {e}")
