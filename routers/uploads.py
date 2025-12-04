# routers/uploads.py

from fastapi import (
    APIRouter, UploadFile, File, Form,
    Depends, HTTPException, Path, Request, Query
)
from typing import Optional
from datetime import datetime
import boto3
import os
import re
import tempfile
from pathlib import Path as PathLib
from botocore.exceptions import ClientError, NoCredentialsError

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
    get_optional_auth,
)

from core.supabase_client import get_supabase_client
from core.permission_helpers import (
    is_admin,
    require_building_access,
    require_units_access,
    require_document_access,
)
from core.stripe_helpers import verify_stripe_session, verify_stripe_payment_intent
from core.rate_limiter import require_rate_limit, get_rate_limit_identifier
from core.logging_config import logger

router = APIRouter(
    prefix="/uploads",
    tags=["Uploads"],
)

# -----------------------------------------------------
# Sanitize helper (using centralized utility)
# -----------------------------------------------------
from core.utils import sanitize

# -----------------------------------------------------
# Filename sanitizer
# -----------------------------------------------------
def safe_filename(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)

# -----------------------------------------------------
# Normalize swagger-like values
# -----------------------------------------------------
def normalize_uuid_like(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if not v or v.lower() in {"string", "null", "undefined"}:
        return None
    return v

# -----------------------------------------------------
# AWS S3 (using centralized utility)
# -----------------------------------------------------
from core.s3_client import get_s3

# -----------------------------------------------------
# Building access check
# -----------------------------------------------------
def verify_user_building_access(current_user: CurrentUser, building_id: str):
    if current_user.role in ["admin", "super_admin", "aoao"]:
        return

    client = get_supabase_client()
    rows = (
        client.table("user_building_access")
        .select("*")
        .eq("user_id", current_user.id)
        .eq("building_id", building_id)
        .execute()
    ).data

    if not rows:
        raise HTTPException(403, "User does not have access to this building.")

# -----------------------------------------------------
# event_id → building_id
# -----------------------------------------------------
def get_event_info(event_id: str | None):
    """Get building_id for an event. Returns (building_id, None) for compatibility."""
    normalized = normalize_uuid_like(event_id)
    if not normalized:
        return None, None

    client = get_supabase_client()
    rows = (
        client.table("events")
        .select("building_id")
        .eq("id", normalized)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(404, "Event not found")

    return rows[0]["building_id"], None

# -----------------------------------------------------
# unit_id → building_id
# -----------------------------------------------------
def get_unit_building(unit_id: str | None):
    normalized = normalize_uuid_like(unit_id)
    if not normalized:
        return None

    client = get_supabase_client()
    rows = (
        client.table("units")
        .select("building_id")
        .eq("id", normalized)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(400, "Unit not found")

    return rows[0]["building_id"]

# -----------------------------------------------------
# UPLOAD DOCUMENT — NOW UNIT-AWARE
# -----------------------------------------------------
@router.post(
    "/",
    summary="Upload a document and create a document record",
    dependencies=[Depends(requires_permission("upload:write"))],
)
async def upload_document(
    file: UploadFile = File(...),

    # Required filename
    filename: str = Form(...),

    # New full compatibility
    building_id: str | None = Form(None),
    event_id: str | None = Form(None),
    
    # NEW — Multiple units and contractors support
    unit_ids: str | None = Form(None, description="JSON array of unit IDs: [\"uuid1\", \"uuid2\"]"),
    contractor_ids: str | None = Form(None, description="JSON array of contractor IDs: [\"uuid1\", \"uuid2\"]"),

    category: str | None = Form(None),

    # Visibility toggle (redaction is now manual via separate endpoint)
    is_public: bool = Form(True, description="Whether the document should be public (true = public, false = private)"),

    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Uploads a file to S3 AND creates a Supabase document record.
    Supports: building_id, event_id, unit_ids (array).
    Requires: filename (custom filename for the uploaded file).
    """

    # Normalize values
    building_id = normalize_uuid_like(building_id)
    event_id = normalize_uuid_like(event_id)
    
    # Validate building_id is not None (required by schema) - but allow it to be set later from event/unit
    # We'll validate it's set before creating the document record
    
    # Parse unit_ids and contractor_ids from JSON strings
    parsed_unit_ids = []
    if unit_ids:
        try:
            import json
            parsed_unit_ids = json.loads(unit_ids)
            if not isinstance(parsed_unit_ids, list):
                parsed_unit_ids = []
        except Exception:
            parsed_unit_ids = []
    
    parsed_contractor_ids = []
    if contractor_ids:
        try:
            import json
            parsed_contractor_ids = json.loads(contractor_ids)
            if not isinstance(parsed_contractor_ids, list):
                parsed_contractor_ids = []
        except Exception:
            parsed_contractor_ids = []
    
    # Remove duplicates
    parsed_unit_ids = list(dict.fromkeys(parsed_unit_ids))
    parsed_contractor_ids = list(dict.fromkeys(parsed_contractor_ids))

    # -----------------------------------------------------
    # Resolve building from ANY provided input
    # -----------------------------------------------------

    # If event is provided → derive building
    if event_id:
        event_building, _ = get_event_info(event_id)
        
        if building_id and building_id != event_building:
            raise HTTPException(400, "Event does not belong to building.")
        building_id = event_building

    # If units provided → derive building from first unit and validate all belong to same building
    if parsed_unit_ids:
        # Check for duplicates
        if len(parsed_unit_ids) != len(set(parsed_unit_ids)):
            raise HTTPException(400, "Duplicate unit IDs are not allowed")
        
        unit_building = get_unit_building(parsed_unit_ids[0])
        if building_id and building_id != unit_building:
            raise HTTPException(400, "Unit does not belong to the specified building")
        building_id = unit_building
        
        # Validate all units belong to same building
        for uid in parsed_unit_ids[1:]:
            uid_building = get_unit_building(uid)
            if uid_building != building_id:
                raise HTTPException(400, f"All units must belong to the same building. Unit {uid} belongs to {uid_building}, expected {building_id}.")
    
    # Validate contractors exist
    if parsed_contractor_ids:
        # Check for duplicates
        if len(parsed_contractor_ids) != len(set(parsed_contractor_ids)):
            raise HTTPException(400, "Duplicate contractor IDs are not allowed")
        
        client = get_supabase_client()
        for cid in parsed_contractor_ids:
            contractor_rows = (
                client.table("contractors")
                .select("id")
                .eq("id", cid)
                .execute()
            ).data
            if not contractor_rows:
                raise HTTPException(400, f"Contractor {cid} does not exist")

    # If building not provided → error
    if not building_id:
        raise HTTPException(400, "Must provide either event_id, unit_ids, or building_id.")

    # -----------------------------------------------------
    # Permission checks: ensure user has access to building and all units
    # -----------------------------------------------------
    if not is_admin(current_user):
        # Check building access
        require_building_access(current_user, building_id)
        
        # Check unit access (if units provided)
        if parsed_unit_ids:
            # AOAO roles can upload documents for their building even without unit access
            if current_user.role not in ["aoao", "aoao_staff"]:
                require_units_access(current_user, parsed_unit_ids)

    # -----------------------------------------------------
    # Prepare S3 key
    # -----------------------------------------------------
    s3, bucket, region = get_s3()

    # Use the provided filename (required), sanitize it
    if not filename or not filename.strip():
        raise HTTPException(400, "filename is required and cannot be empty")
    clean_filename = safe_filename(filename.strip())

    safe_category = (
        category.strip().replace(" ", "_").lower()
        if category else "general"
    )

    # NEW S3 path rules
    if event_id:
        # Use first unit if available, otherwise 'none'
        first_unit = parsed_unit_ids[0] if parsed_unit_ids else 'none'
        s3_key = f"events/{event_id}/units/{first_unit}/documents/{safe_category}/{clean_filename}"

    elif parsed_unit_ids:
        s3_key = f"units/{parsed_unit_ids[0]}/documents/{safe_category}/{clean_filename}"

    else:
        s3_key = f"buildings/{building_id}/documents/{safe_category}/{clean_filename}"
    
    # Final validation: building_id must be set at this point
    if not building_id:
        raise HTTPException(400, "building_id is required and cannot be null")
    
    # Validate building exists
    client = get_supabase_client()
    building_rows = (
        client.table("buildings")
        .select("id")
        .eq("id", building_id)
        .execute()
    ).data
    if not building_rows:
        raise HTTPException(400, f"Building {building_id} does not exist")

    # -----------------------------------------------------
    # Save file temporarily and upload to S3
    # -----------------------------------------------------
    temp_file_path = None

    try:
        # Save uploaded file to temporary location
        file_extension = PathLib(file.filename or clean_filename).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file_path = temp_file.name
            # Read and write the file content
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()

        # Upload file to S3
        try:
            s3.upload_file(
                Filename=temp_file_path,
                Bucket=bucket,
                Key=s3_key,
                ExtraArgs={"ContentType": file.content_type},
            )
        except Exception as e:
            raise HTTPException(500, f"S3 upload error: {e}")
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                print(f"Warning: Failed to delete temp file {temp_file_path}: {e}")

    # Generate presigned URL for immediate use (expires in 1 day)
    # Note: For long-term access, use the /documents/{id}/download endpoint
    presigned_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=86400,  # 1 day
    )

    # -----------------------------------------------------
    # Create document record
    # -----------------------------------------------------
    client = get_supabase_client()

    payload = sanitize({
        "building_id": building_id,
        "event_id": event_id,
        "category": category,
        "filename": clean_filename,
        "s3_key": s3_key,
        "content_type": file.content_type,
        "uploaded_by": current_user.id,
        "is_redacted": False,  # Manual redaction is handled via separate endpoint
        "is_public": is_public,
        # Note: Don't store download_url - it expires. Use /documents/{id}/download endpoint instead
    })

    # Step 1 — Insert
    insert_res = (
        client.table("documents")
        .insert(payload)
        .execute()
    )

    if not insert_res.data:
        raise HTTPException(500, "Insert returned no data")

    doc_id = insert_res.data[0]["id"]

    # Step 2 — Create junction table entries for units
    if parsed_unit_ids:
        for unit_id_val in parsed_unit_ids:
            try:
                client.table("document_units").insert({
                    "document_id": doc_id,
                    "unit_id": unit_id_val
                }).execute()
            except Exception as e:
                # Ignore duplicate key errors (unique constraint)
                if "duplicate" not in str(e).lower():
                    print(f"Warning: Failed to create document_unit relationship: {e}")
    
    # Step 3 — Create junction table entries for contractors
    if parsed_contractor_ids:
        for contractor_id_val in parsed_contractor_ids:
            try:
                client.table("document_contractors").insert({
                    "document_id": doc_id,
                    "contractor_id": contractor_id_val
                }).execute()
            except Exception as e:
                # Ignore duplicate key errors (unique constraint)
                if "duplicate" not in str(e).lower():
                    print(f"Warning: Failed to create document_contractor relationship: {e}")

    # Step 4 — Fetch with relations
    fetch_res = (
        client.table("documents")
        .select("*")
        .eq("id", doc_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Created document not found")
    
    document = fetch_res.data[0]
    
    # Enrich with units and contractors
    # Fetch units and contractors from junction tables
    document_units = (
        client.table("document_units")
        .select("unit_id, units(*)")
        .eq("document_id", doc_id)
        .execute()
    )
    units = []
    if document_units.data:
        for row in document_units.data:
            if row.get("units"):
                units.append(row["units"])
    
    document_contractors = (
        client.table("document_contractors")
        .select("contractor_id, contractors(*)")
        .eq("document_id", doc_id)
        .execute()
    )
    contractors = []
    if document_contractors.data:
        for row in document_contractors.data:
            if row.get("contractors"):
                contractor = row["contractors"]
                # Enrich contractor with roles
                contractor = enrich_contractor_with_roles(contractor)
                contractors.append(contractor)
    
    document["units"] = units
    document["contractors"] = contractors
    document["unit_ids"] = [u["id"] for u in units]
    document["contractor_ids"] = [c["id"] for c in contractors]


# -----------------------------------------------------
# Helper — Enrich contractor with roles
# -----------------------------------------------------
def enrich_contractor_with_roles(contractor: dict) -> dict:
    """Add roles array to contractor dict."""
    contractor_id = contractor.get("id")
    if not contractor_id:
        contractor["roles"] = []
        return contractor
    
    client = get_supabase_client()
    
    # Get roles for this contractor
    role_result = (
        client.table("contractor_role_assignments")
        .select("role_id, contractor_roles(name)")
        .eq("contractor_id", contractor_id)
        .execute()
    )
    
    roles = []
    if role_result.data:
        for row in role_result.data:
            if row.get("contractor_roles") and row["contractor_roles"].get("name"):
                roles.append(row["contractor_roles"]["name"])
    
    contractor["roles"] = roles
    return contractor

    # -----------------------------------------------------
    # Update event with s3_key if event_id is provided
    # -----------------------------------------------------
    if event_id:
        try:
            client.table("events").update({
                "s3_key": s3_key
            }).eq("id", event_id).execute()
        except Exception as e:
            # Log error but don't fail the upload
            print(f"Warning: Failed to update event {event_id} with s3_key: {e}")

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------
    return {
        "upload": {
            "filename": clean_filename,
            "s3_key": s3_key,
            "presigned_url": presigned_url,  # Valid for 1 day
            "uploaded_at": datetime.utcnow().isoformat(),
        },
        "document": document,
    }


# -----------------------------------------------------
# GET PRESIGNED URL FOR DOCUMENT (on-demand) - HYBRID ACCESS
# -----------------------------------------------------
@router.get(
    "/documents/{document_id}/download",
    summary="Get a presigned URL for downloading a document (hybrid: free/paid/auth)",
)
async def get_document_download_url(
    request: Request,
    document_id: str = Path(..., description="Document ID"),
    stripe_session_id: Optional[str] = Query(None, description="Stripe Checkout Session ID (for paid documents)"),
    stripe_payment_intent_id: Optional[str] = Query(None, description="Stripe Payment Intent ID (alternative to session)"),
    current_user: Optional[CurrentUser] = Depends(get_optional_auth),
):
    """
    Generates a fresh presigned URL for a document.
    
    Access Control (Hybrid Approach):
    - PUBLIC documents (is_public=True): 
      * Free access without authentication (rate limited), OR
      * Valid Stripe payment verification (for paid public documents)
    - PRIVATE documents (is_public=False): Only accessible by:
      1. User is the document owner (uploader) - highest priority
      2. Authenticated user with document access permissions
      NOTE: Stripe payments are NOT allowed for private documents
    
    Use this endpoint when download_url has expired or doesn't exist.
    """
    client = get_supabase_client()

    # Fetch document with access information
    rows = (
        client.table("documents")
        .select("s3_key, is_public, building_id, uploaded_by")
        .eq("id", document_id)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(404, "Document not found")

    doc = rows[0]

    if not doc.get("s3_key"):
        raise HTTPException(400, "Document has no S3 key")

    is_public = doc.get("is_public", False)
    uploaded_by = doc.get("uploaded_by")
    
    # ============================================================
    # ACCESS CONTROL LOGIC
    # ============================================================
    access_granted = False
    access_method = None
    
    # PUBLIC DOCUMENTS: Check is_public flag
    if is_public:
        # Public documents can be accessed via:
        # 1. Free access (no auth/payment needed) - rate limited
        # 2. Stripe payment (for paid public documents)
        
        # Check if Stripe payment provided for paid public documents
        if stripe_session_id:
            if verify_stripe_session(stripe_session_id, document_id):
                access_granted = True
                access_method = "stripe_session"
                logger.info(f"Public document {document_id} accessed via Stripe session {stripe_session_id}")
            else:
                raise HTTPException(
                    status_code=402,
                    detail="Payment verification failed. Please ensure your payment was completed successfully."
                )
        elif stripe_payment_intent_id:
            if verify_stripe_payment_intent(stripe_payment_intent_id, document_id):
                access_granted = True
                access_method = "stripe_payment_intent"
                logger.info(f"Public document {document_id} accessed via Stripe payment intent {stripe_payment_intent_id}")
            else:
                raise HTTPException(
                    status_code=402,
                    detail="Payment verification failed. Please ensure your payment was completed successfully."
                )
        else:
            # Free public document - accessible without auth/payment, but rate limited
            access_granted = True
            access_method = "free"
            
            # Apply rate limiting for free public documents (prevent abuse)
            user_id = current_user.id if current_user else None
            identifier = get_rate_limit_identifier(request, user_id)
            # More lenient rate limit for free documents: 20 requests per minute
            require_rate_limit(request, identifier, max_requests=20, window_seconds=60)
    
    # PRIVATE DOCUMENTS: Only owner or users with permissions (NO Stripe payments)
    else:
        # Option 1: Check if user is the document owner (uploader)
        if current_user and uploaded_by:
            # Compare using auth_user_id for consistency
            user_id_to_check = getattr(current_user, "auth_user_id", None) or str(current_user.id)
            uploaded_by_str = str(uploaded_by)
            
            if user_id_to_check == uploaded_by_str:
                access_granted = True
                access_method = "owner"
                logger.info(f"Private document {document_id} accessed by owner {user_id_to_check}")
        
        # Option 2: Authenticated user with document access permissions
        if not access_granted and current_user:
            try:
                # Check if user has access via permissions
                require_document_access(current_user, document_id)
                access_granted = True
                access_method = "authenticated"
            except HTTPException:
                # User doesn't have access
                pass
        
        # Private documents do NOT allow Stripe payments
        # If Stripe payment provided for private document, reject it
        if not access_granted:
            if stripe_session_id or stripe_payment_intent_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied. This document is private and cannot be purchased. Only the uploader or users with appropriate permissions can access this document."
                )
            else:
                # No owner match, no permissions, and no payment attempted
                raise HTTPException(
                    status_code=403,
                    detail="Access denied. This document is private. Only the uploader or users with appropriate permissions can access this document."
                )
    
    # ============================================================
    # GENERATE PRESIGNED URL
    # ============================================================
    if not access_granted:
        raise HTTPException(403, "Access denied")
    
    s3, bucket, region = get_s3()

    try:
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": doc["s3_key"]},
            ExpiresIn=3600,  # 1 hour
        )
        
        logger.info(f"Generated presigned URL for document {document_id} via {access_method}")
        
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for document {document_id}: {e}")
        raise HTTPException(500, f"Failed to generate presigned URL: {e}")

    return {
        "document_id": document_id,
        "download_url": presigned_url,
        "expires_in": 3600,
        "access_method": access_method,
        "is_public": is_public,
    }

