from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import boto3
import os
from datetime import datetime
from botocore.exceptions import NoCredentialsError, ClientError
from src.routers.auth import get_current_user  # ✅ updated path

router = APIRouter(prefix="/upload", tags=["Uploads"])

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
@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    complex_name: str = Form(...),
    category: str = Form(...),
    scope: str = Form("complex"),        # "complex" or "unit"
    unit_name: str | None = Form(None)   # only required when scope == "unit"
):
    """
    Uploads a file to S3 in the correct hierarchy.

    Folder structure:
        complexes/{complex_name}/complex/{category}/{filename}
        complexes/{complex_name}/units/{unit_name}/{category}/{filename}
    """
    s3, bucket_name, region = get_s3_client()

    try:
        # Build S3 key path
        if scope == "unit":
            if not unit_name:
                raise HTTPException(status_code=400, detail="unit_name is required for unit-level uploads.")
            s3_path = f"complexes/{complex_name}/units/{unit_name}/{category}/{file.filename}"
        else:
            s3_path = f"complexes/{complex_name}/complex/{category}/{file.filename}"

        # Upload file to S3
        s3.upload_fileobj(file.file, bucket_name, s3_path)

        # Generate public URL
        file_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_path}"

        return {
            "message": "File uploaded successfully.",
            "file_url": file_url,
            "uploaded_at": datetime.utcnow().isoformat(),
            "path": s3_path,
        }

    except (NoCredentialsError, ClientError) as e:
        raise HTTPException(status_code=500, detail=f"AWS upload failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
