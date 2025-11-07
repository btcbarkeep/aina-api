from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
import boto3, os
from datetime import datetime
from botocore.exceptions import NoCredentialsError, ClientError
from src.routers.dependencies import get_current_user

router = APIRouter(prefix="/upload", tags=["Uploads"])

def get_s3_client():
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
    AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME]):
        raise RuntimeError("Missing AWS S3 credentials in environment variables.")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
    return s3, AWS_BUCKET_NAME, AWS_REGION

@router.post("/", summary="Upload File to S3")
async def upload_file(
    file: UploadFile = File(...),
    complex_name: str = Form(...),
    category: str = Form(...),
    scope: str = Form("complex"),
    unit_name: str | None = Form(None),
    current_user: str = Depends(get_current_user)
):
    try:
        s3, bucket, region = get_s3_client()
        safe_complex = complex_name.strip().replace(" ", "_").upper()
        safe_category = category.strip().replace(" ", "_").lower()

        if scope == "unit":
            if not unit_name:
                raise HTTPException(status_code=400, detail="unit_name is required when scope='unit'")
            safe_unit = unit_name.strip().replace(" ", "_").upper()
            key = f"complexes/{safe_complex}/units/{safe_unit}/{safe_category}/{file.filename}"
        else:
            key = f"complexes/{safe_complex}/complex/{safe_category}/{file.filename}"

        s3.upload_fileobj(file.file, bucket, key, ExtraArgs={"ContentType": file.content_type})
        url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

        return {"filename": file.filename, "path": key, "url": url, "uploaded_by": current_user, "uploaded_at": datetime.utcnow().isoformat()}

    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="AWS credentials not found.")
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error uploading to S3: {e}")
