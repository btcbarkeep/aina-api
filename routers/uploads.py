from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import boto3
import os
from datetime import datetime
from botocore.exceptions import NoCredentialsError, ClientError

router = APIRouter()


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
    return s3, AWS_BUCKET_NAME, AWS_REGION


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    property_name: str = Form(...),
    category: str = Form("misc")
):
    """
    Uploads a file to S3 under:
        properties/{property_name}/{category}/{filename}
    and returns its S3 download URL + metadata.
    """
    try:
        s3, bucket, region = get_s3_client()

        # Normalize names
        safe_property = property_name.strip().replace(" ", "-").lower()
        safe_category = category.strip().replace(" ", "_").lower()

        # Build key
        key = f"properties/{safe_property}/{safe_category}/{file.filename}"

        # Upload to S3
        s3.upload_fileobj(
            Fileobj=file.file,
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": file.content_type},
        )

        # Public URL
        download_url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

        return {
            "filename": file.filename,
            "property": safe_property,
            "category": safe_category,
            "content_type": file.content_type,
            "uploaded_at": datetime.utcnow().isoformat(),
            "download_url": download_url,
        }

    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="AWS credentials not found.")
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error uploading to S3: {e}")
