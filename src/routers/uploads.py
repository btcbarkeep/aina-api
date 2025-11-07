from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
import boto3
import os
from datetime import datetime
from botocore.exceptions import NoCredentialsError, ClientError
from src.routers.auth import get_current_user  # optional if you use auth

router = APIRouter(prefix="/upload", tags=["Uploads"])

# -----------------------------------------------------
#  AWS CONFIGURATION
# -----------------------------------------------------
def get_s3_client():
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
    return s3, AWS_BUCKET_NAME


# -----------------------------------------------------
#  UPLOAD FILE
# -----------------------------------------------------
@router.post("/", summary="Upload File to S3")
async def upload_file(
    file: UploadFile = File(...),
    complex_name: str = Form(...),
    category: str = Form(...),
    scope: str = Form("complex"),        # "complex" or "unit"
    unit_name: str | None = Form(None)   # only required when scope == "unit"
):
    """
    Uploads a file to S3 under the correct hierarchy.
    """
    s3, bucket_name = get_s3_client()

    # Construct S3 path
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}_{file.filename}"

    if scope == "complex":
        s3_key = f"complexes/{complex_name}/complex/{category}/{filename}"
    elif scope == "unit" and unit_name:
        s3_key = f"complexes/{complex_name}/units/{unit_name}/{category}/{filename}"
    else:
        raise HTTPException(status_code=400, detail="Invalid scope or missing unit_name")

    try:
        s3.upload_fileobj(file.file, bucket_name, s3_key)
    except (NoCredentialsError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "message": "File uploaded successfully",
        "s3_key": s3_key,
        "bucket": bucket_name,
    }
