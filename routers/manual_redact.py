"""
Manual PDF Redaction Router

This router handles manual PDF redaction where users draw redaction boxes
on a PDF and the server applies them using PyMuPDF.
"""

from fastapi import (
    APIRouter, UploadFile, File, Form,
    Depends, HTTPException
)
from pydantic import BaseModel, Field
from typing import List
import io
import tempfile
import os
from pathlib import Path as PathLib

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False
    fitz = None

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from core.logging_config import logger

# S3 upload logic (copied from uploads router to avoid circular imports)
import boto3
def get_s3():
    key = os.getenv("AWS_ACCESS_KEY_ID")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    bucket = os.getenv("AWS_BUCKET_NAME")
    region = os.getenv("AWS_REGION", "us-east-2")

    if not all([key, secret, bucket]):
        raise RuntimeError("Missing AWS credentials")

    client = boto3.client(
        "s3",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name=region,
    )

    return client, bucket, region

router = APIRouter(
    prefix="/documents",
    tags=["Manual Redaction"],
)


# ======================================================
# Models
# ======================================================

class RedactionBox(BaseModel):
    """A single redaction box with coordinates."""
    page: int = Field(..., description="Page number (0-indexed or 1-indexed, will be normalized)")
    x: float = Field(..., description="X coordinate (left)")
    y: float = Field(..., description="Y coordinate (top)")
    width: float = Field(..., description="Width of the redaction box")
    height: float = Field(..., description="Height of the redaction box")


# ======================================================
# Manual Redaction Endpoint
# ======================================================

@router.post(
    "/redact-manual",
    summary="Apply manual redactions to a PDF",
    dependencies=[Depends(requires_permission("upload:write"))],
)
async def redact_manual(
    file: UploadFile = File(..., description="PDF file to redact"),
    redaction_boxes: str = Form(..., description="JSON array of redaction boxes"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Apply manual redactions to a PDF file.
    
    Receives:
    - PDF file
    - JSON array of redaction boxes: [{"page": 1, "x": 100, "y": 200, "width": 150, "height": 30}, ...]
    
    Returns:
    - Final redacted PDF URL (S3 presigned URL)
    """
    
    if not FITZ_AVAILABLE:
        raise HTTPException(500, "PyMuPDF (fitz) is required for PDF redaction. Install with: pip install PyMuPDF")
    
    # Validate file is PDF
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        if file.content_type != 'application/pdf':
            raise HTTPException(400, "File must be a PDF")
    
    # Parse redaction boxes
    import json
    try:
        boxes_data = json.loads(redaction_boxes)
        boxes = [RedactionBox(**box) for box in boxes_data]
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON in redaction_boxes: {e}")
    except Exception as e:
        raise HTTPException(400, f"Invalid redaction box format: {e}")
    
    if not boxes:
        raise HTTPException(400, "At least one redaction box is required")
    
    logger.info(f"Applying {len(boxes)} redaction box(es) to PDF: {file.filename}")
    
    # Read PDF file
    pdf_content = await file.read()
    
    # Open PDF with PyMuPDF
    try:
        doc = fitz.open(stream=pdf_content, filetype="pdf")
    except Exception as e:
        raise HTTPException(400, f"Failed to open PDF: {e}")
    
    # Apply redactions
    try:
        for box in boxes:
            # Normalize page number (assume frontend uses 1-indexed, PyMuPDF uses 0-indexed)
            page_num = box.page - 1 if box.page > 0 else box.page
            
            if page_num < 0 or page_num >= len(doc):
                logger.warning(f"Skipping redaction box on invalid page {box.page} (PDF has {len(doc)} pages)")
                continue
            
            page = doc[page_num]
            
            # Create rectangle for redaction
            # PDF coordinates have origin at bottom-left, but canvas uses top-left
            # Convert from canvas coordinates (top-left origin) to PDF coordinates (bottom-left origin)
            page_height = page.rect.height
            page_width = page.rect.width
            
            # Convert coordinates: y_pdf = page_height - y_canvas - height
            y_pdf = page_height - box.y - box.height
            
            # Ensure coordinates are within page bounds
            x1 = max(0, min(box.x, page_width))
            y1 = max(0, min(y_pdf, page_height))
            x2 = max(0, min(box.x + box.width, page_width))
            y2 = max(0, min(y_pdf + box.height, page_height))
            
            rect = fitz.Rect(x1, y1, x2, y2)
            
            # Add redaction annotation (this marks the area for redaction)
            page.add_redact_annot(rect, fill=(0, 0, 0))  # Black fill
            
            logger.debug(f"Added redaction box on page {box.page}: {rect}")
        
        # Apply all redactions (this actually removes the content)
        for page_num in range(len(doc)):
            page = doc[page_num]
            page.apply_redactions()
        
        logger.info(f"Successfully applied redactions to {len(doc)} page(s)")
        
    except Exception as e:
        doc.close()
        raise HTTPException(500, f"Failed to apply redactions: {e}")
    
    # Save redacted PDF to BytesIO
    try:
        pdf_bytes = doc.tobytes()
        doc.close()
    except Exception as e:
        doc.close()
        raise HTTPException(500, f"Failed to save redacted PDF: {e}")
    
    # Upload to S3
    try:
        s3, bucket, region = get_s3()
        
        # Generate S3 key (use timestamp to avoid conflicts)
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        original_filename = PathLib(file.filename or "document.pdf").stem
        s3_key = f"redacted/{timestamp}_{original_filename}_redacted.pdf"
        
        # Upload to S3
        s3.upload_fileobj(
            Fileobj=io.BytesIO(pdf_bytes),
            Bucket=bucket,
            Key=s3_key,
            ExtraArgs={"ContentType": "application/pdf"},
        )
        
        logger.info(f"Uploaded redacted PDF to S3: {s3_key}")
        
        # Generate presigned URL (valid for 1 day)
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=86400,  # 1 day
        )
        
        return {
            "success": True,
            "document_url": presigned_url,
            "s3_key": s3_key,
            "redaction_count": len(boxes),
        }
        
    except Exception as e:
        logger.error(f"Failed to upload redacted PDF to S3: {e}")
        raise HTTPException(500, f"Failed to upload redacted PDF: {e}")

