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
            # Extract coordinates
            x = box.x
            y = box.y
            w = box.width
            h = box.height
            page_index = box.page - 1  # Convert 1-indexed to 0-indexed
            
            if page_index < 0 or page_index >= len(doc):
                logger.warning(f"Skipping redaction box on invalid page {box.page} (PDF has {len(doc)} pages)")
                continue
            
            page = doc.load_page(page_index)
            page_height = page.rect.height
            
            # Convert top-left origin (canvas) to bottom-left origin (PDF)
            # incoming: x, y, width, height (top-left origin)
            pdf_y = page_height - (y + h)
            
            # Create rectangle in PDF coordinate system
            rect = fitz.Rect(x, pdf_y, x + w, pdf_y + h)
            
            # Add redaction annotation with black fill
            page.add_redact_annot(rect, fill=(0, 0, 0))
            
            logger.debug(f"Added redaction box on page {box.page}: {rect} (canvas y={y} -> PDF y={pdf_y})")
        
        # Apply all redactions after adding all annotations
        # This actually removes the content and applies black fill
        for page in doc:
            page.apply_redactions()
        
        logger.info(f"Successfully applied redactions to {len(doc)} page(s)")
        
    except Exception as e:
        doc.close()
        raise HTTPException(500, f"Failed to apply redactions: {e}")
    
    # Save redacted PDF to BytesIO
    try:
        output_pdf = io.BytesIO()
        doc.save(output_pdf, deflate=True, clean=True)
        output_pdf.seek(0)
        pdf_bytes = output_pdf.read()
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

