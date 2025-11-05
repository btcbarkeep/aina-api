from fastapi import APIRouter, UploadFile, File, HTTPException
import boto3
import os
from botocore.exceptions import NoCredentialsError, ClientError

router = APIRouter()

# --- AWS CONFIGURATION ---
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME]):
    raise RuntimeError("Missing AWS S3 credentials or bucket name in environment variables.")

# Initialize S3 client
s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)

# --- ROUTES ---
@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file to the configured S3 bucket.
    Returns a JSON response with a public download URL.
    """
    try:
        s3.upload_fileobj(
            Fileobj=file.file,
            Bucket=AWS_BUCKET_NAME,
            Key=file.filename,
            ExtraArgs={"ContentType": file.content_type, "ACL": "public-read"},
        )

        download_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{file.filename}"

        return {
            "filename": file.filename,
            "content_type": file.content_type,
            "download_url": download_url,
        }

    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="AWS credentials not found.")
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error uploading to S3: {e}")

