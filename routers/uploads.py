import os, uuid
from typing import Optional
import boto3
from botocore.config import Config
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/upload", tags=["uploads"])

AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
S3_BUCKET = os.getenv("S3_BUCKET")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", None)

_session = boto3.session.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=AWS_REGION,
)
_s3 = _session.client("s3", endpoint_url=S3_ENDPOINT_URL, config=Config(s3={"addressing_style": "virtual"}))

class PresignRequest(BaseModel):
    filename: str
    content_type: Optional[str] = "application/pdf"
    prefix: Optional[str] = "uploads/"

class PresignResponse(BaseModel):
    url: str
    method: str = "PUT"
    headers: dict
    key: str

@router.post("/url", response_model=PresignResponse)
def create_presigned_upload_url(req: PresignRequest):
    if not S3_BUCKET:
        raise HTTPException(status_code=500, detail="S3_BUCKET not configured")

    key = f"{req.prefix}{uuid.uuid4().hex}-{req.filename}"
    try:
        url = _s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": S3_BUCKET, "Key": key, "ContentType": req.content_type or "application/pdf"},
            ExpiresIn=600,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to presign: {e}")

    return PresignResponse(url=url, headers={"Content-Type": req.content_type or "application/pdf"}, key=key)
