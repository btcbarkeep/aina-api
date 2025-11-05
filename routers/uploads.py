from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import os
from uuid import uuid4
import boto3
from botocore.exceptions import BotoCoreError, ClientError

router = APIRouter(prefix="/upload", tags=["upload"])

class PresignRequest(BaseModel):
    filename: str = Field(..., description="Original filename, e.g. report.pdf")
    content_type: str = Field(..., description="MIME type, e.g. application/pdf")

def _require_env(var: str) -> str:
    val = os.getenv(var)
    if not val:
        raise HTTPException(status_code=500, detail=f"{var} not configured")
    return val

@router.post("/url")
def create_presigned_url(req: PresignRequest):
    """
    Returns a one-time URL the browser can PUT the file to S3 with.
    Response shape:
    {
      "url": "<presigned PUT url>",
      "method": "PUT",
      "headers": {"Content-Type": "<mime>"},
      "key": "uploads/<uuid>-<safe-filename>"
    }
    """
    bucket = _require_env("S3_BUCKET")
    region = _require_env("AWS_REGION")  # e.g. us-east-2

    # Basic filename hardening (keep it simple)
    safe_name = req.filename.replace("/", "_").replace("\\", "_").strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    key = f"uploads/{uuid4().hex}-{safe_name}"

    try:
        s3 = boto3.client("s3", region_name=region)
        url = s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ContentType": req.content_type,
            },
            ExpiresIn=600,  # 10 minutes
        )
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to presign: {e}")

    return {
        "url": url,
        "method": "PUT",
        "headers": {"Content-Type": req.content_type},
        "key": key,
    }
