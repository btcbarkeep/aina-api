from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query
import boto3
import os
from datetime import datetime, timedelta
from botocore.exceptions import NoCredentialsError, ClientError
from src.dependencies import get_active_user

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

        # Upload (no ACL, since bucket is private)
        s3.upload_fileobj(
            Fileobj=file.file,
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": file.content_type},
        )

        # Generate presigned URL (valid for 24 hours)
        presigned_url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=86400,  # 24 hours (seconds)
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
#  DELETE FILE (Protected)
# -----------------------------------------------------
@router.delete("/", dependencies=[Depends(get_active_user)])
def delete_file(
    s3_key: str = Query(..., description="Full S3 object key to delete, e.g. 'complexes/BUILDING/complex/notices/file.pdf'")
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
