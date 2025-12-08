# routers/document_email.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime
import pytz

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.logging_config import logger
from core.notifications import send_email
from core.s3_client import get_s3
from models.document_email import DocumentEmailRequest
from models.document_email_log import DocumentEmailLogRead
from core.permission_helpers import require_document_access
from core.role_subscriptions import check_user_has_active_subscription

router = APIRouter(
    prefix="/documents",
    tags=["Document Email"],
)

# Presigned URL expiration for email links (7 days)
EMAIL_PRESIGNED_URL_EXPIRY_SECONDS = 604800  # 7 days

# Hawaii timezone
HST = pytz.timezone('Pacific/Honolulu')


def get_hst_time() -> datetime:
    """Get current time in Hawaii Standard Time (HST)."""
    return datetime.now(HST)


def format_hst_time(dt: datetime = None) -> str:
    """Format datetime in HST timezone for display."""
    if dt is None:
        dt = get_hst_time()
    elif dt.tzinfo is None:
        # If naive datetime, assume it's UTC and convert to HST
        dt = pytz.UTC.localize(dt).astimezone(HST)
    else:
        # Convert to HST
        dt = dt.astimezone(HST)
    return dt.strftime('%Y-%m-%d %H:%M:%S %Z')


@router.post("/send-email", summary="Send documents via email")
def send_documents_email(
    payload: DocumentEmailRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Send multiple documents (up to 5) via email to multiple recipients.
    
    **Permissions:**
    - Admin, super_admin: Can always send
    - AOAO, Property Manager, Owner, Contractor: Must have active paid subscription (or active trial)
    
    **Features:**
    - Sends documents as email attachments (if S3 files) or download links
    - Sends to multiple recipients (email addresses entered by sender)
    - Sends receipt/confirmation email to sender
    - Generates presigned URLs valid for 7 days
    """
    # Check if user has permission to send documents
    # Admin and super_admin can always send
    if current_user.role in ["admin", "super_admin"]:
        # Admins can always send, no subscription check needed
        pass
    elif current_user.role in ["aoao", "property_manager", "owner", "contractor"]:
        # These roles require active paid subscription (or active trial)
        # Fetch subscription info if not already loaded
        subscription_tier = current_user.subscription_tier
        subscription_status = current_user.subscription_status
        is_trial = current_user.is_trial
        trial_ends_at = current_user.trial_ends_at
        
        # If subscription info not in current_user, fetch it
        if not subscription_tier:
            from core.subscription_helpers import get_user_subscription
            sub = get_user_subscription(current_user.auth_user_id, current_user.role)
            if sub:
                subscription_tier = sub.get("subscription_tier")
                subscription_status = sub.get("subscription_status")
                is_trial = sub.get("is_trial", False)
                trial_ends_at = sub.get("trial_ends_at")
        
        # Check subscription status
        has_active_sub = check_user_has_active_subscription(
            role=current_user.role,
            subscription_tier=subscription_tier,
            subscription_status=subscription_status,
            is_trial=is_trial,
            trial_ends_at=trial_ends_at,
            contractor_id=current_user.contractor_id,
            pm_company_id=current_user.pm_company_id,
            aoao_organization_id=current_user.aoao_organization_id
        )
        
        if not has_active_sub:
            raise HTTPException(
                403,
                f"Active paid subscription required to send documents. Your current subscription: {subscription_tier or 'free'}"
            )
    else:
        raise HTTPException(
            403,
            f"Your role '{current_user.role}' does not have permission to send documents via email"
        )
    
    client = get_supabase_client()
    
    # Validate and fetch documents
    documents = []
    attachments = []
    download_links = []
    
    for doc_id in payload.document_ids:
        # Fetch document
        doc_result = (
            client.table("documents")
            .select("*")
            .eq("id", doc_id)
            .maybe_single()
            .execute()
        )
        
        if not doc_result.data:
            raise HTTPException(404, f"Document {doc_id} not found")
        
        doc = doc_result.data
        
        # Check document access
        try:
            require_document_access(current_user, doc_id)
        except HTTPException:
            raise HTTPException(
                403, 
                f"You do not have access to document {doc_id}"
            )
        
        documents.append(doc)
        
        # Generate presigned URL for document
        if doc.get("s3_key"):
            try:
                s3, bucket, region = get_s3()
                presigned_url = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket, 'Key': doc["s3_key"]},
                    ExpiresIn=EMAIL_PRESIGNED_URL_EXPIRY_SECONDS
                )
                
                # Try to attach as file, fallback to link if attachment fails
                try:
                    # Download file from S3 for attachment
                    s3_obj = s3.get_object(Bucket=bucket, Key=doc["s3_key"])
                    file_content = s3_obj['Body'].read()
                    
                    filename = doc.get("filename") or doc.get("title", "document") + ".pdf"
                    if not filename.endswith('.pdf'):
                        filename += '.pdf'
                    
                    attachments.append({
                        "filename": filename,
                        "content": file_content
                    })
                except Exception as e:
                    logger.warning(f"Could not attach {doc_id} as file, using link instead: {e}")
                    download_links.append({
                        "title": doc.get("title", "Document"),
                        "url": presigned_url,
                        "expires_in_days": 7
                    })
            except Exception as e:
                logger.error(f"Failed to generate presigned URL for document {doc_id}: {e}")
                raise HTTPException(500, f"Failed to generate download link for document {doc_id}")
        elif doc.get("document_url"):
            # External link document
            download_links.append({
                "title": doc.get("title", "Document"),
                "url": doc["document_url"],
                "expires_in_days": None  # External links don't expire
            })
        else:
            raise HTTPException(
                400, 
                f"Document {doc_id} has no file or URL to send"
            )
    
    # Build email body
    email_body = f"""Aloha,

You are receiving {len(documents)} document(s) from {current_user.full_name or current_user.email} via Aina Protocol.

"""
    
    if payload.message:
        email_body += f"Message from sender:\n{payload.message}\n\n"
    
    if attachments:
        email_body += f"Attached: {len(attachments)} document(s)\n"
    
    if download_links:
        email_body += f"\nDownload Links (valid for 7 days):\n"
        for link in download_links:
            email_body += f"- {link['title']}: {link['url']}\n"
    
    email_body += f"""
---
Aina Protocol
This email was sent on {format_hst_time()}
"""
    
    # Build HTML email body
    html_body = f"""
    <html>
    <body>
        <p>Aloha,</p>
        <p>You are receiving <strong>{len(documents)} document(s)</strong> from <strong>{current_user.full_name or current_user.email}</strong> via Aina Protocol.</p>
    """
    
    if payload.message:
        html_body += f"<p><strong>Message from sender:</strong><br>{payload.message.replace(chr(10), '<br>')}</p>"
    
    if download_links:
        html_body += "<p><strong>Download Links (valid for 7 days):</strong></p><ul>"
        for link in download_links:
            html_body += f'<li><a href="{link["url"]}">{link["title"]}</a></li>'
        html_body += "</ul>"
    
    html_body += f"""
        <hr>
        <p><small>Aina Protocol<br>
        This email was sent on {format_hst_time()}</small></p>
    </body>
    </html>
    """
    
    # Send email to recipients
    email_status = "sent"
    error_message = None
    
    try:
        send_email(
            subject=payload.subject,
            body=email_body,
            recipients=payload.recipient_emails,
            attachments=attachments if attachments else None,
            html_body=html_body
        )
        logger.info(
            f"User {current_user.auth_user_id} sent {len(documents)} document(s) "
            f"to {len(payload.recipient_emails)} recipient(s)"
        )
    except Exception as e:
        logger.error(f"Failed to send document email: {e}")
        email_status = "failed"
        error_message = str(e)
        raise HTTPException(500, f"Failed to send email: {str(e)}")
    finally:
        # Log the email send attempt to database
        try:
            log_data = {
                "sender_user_id": current_user.auth_user_id,
                "sender_email": current_user.email,
                "sender_name": current_user.full_name,
                "recipient_emails": payload.recipient_emails,
                "document_ids": payload.document_ids,
                "subject": payload.subject,
                "message": payload.message if payload.message else None,
                "status": email_status,
                "error_message": error_message,
                "sent_at": get_hst_time().isoformat()
            }
            
            client.table("document_email_logs").insert(log_data).execute()
            logger.debug(f"Document email log created for user {current_user.auth_user_id}")
        except Exception as log_error:
            # Don't fail the request if logging fails
            logger.warning(f"Failed to log document email: {log_error}")
    
    # Send receipt/confirmation email to sender
    sender_email = current_user.email
    if sender_email:
        receipt_body = f"""Aloha {current_user.full_name or 'User'},

This is a confirmation that you successfully sent {len(documents)} document(s) via Aina Protocol.

Recipients:
{chr(10).join(payload.recipient_emails)}

Documents sent:
{chr(10).join([f"- {doc.get('title', 'Untitled')}" for doc in documents])}

Sent on: {format_hst_time()}

---
Aina Protocol
"""
        
        receipt_html = f"""
        <html>
        <body>
            <p>Aloha <strong>{current_user.full_name or 'User'}</strong>,</p>
            <p>This is a confirmation that you successfully sent <strong>{len(documents)} document(s)</strong> via Aina Protocol.</p>
            <p><strong>Recipients:</strong><br>{'<br>'.join(payload.recipient_emails)}</p>
            <p><strong>Documents sent:</strong></p>
            <ul>
                {''.join([f'<li>{doc.get("title", "Untitled")}</li>' for doc in documents])}
            </ul>
            <p><small>Sent on: {format_hst_time()}</small></p>
            <hr>
            <p><small>Aina Protocol</small></p>
        </body>
        </html>
        """
        
        try:
            send_email(
                subject=f"Confirmation: Documents Sent via Aina Protocol",
                body=receipt_body,
                recipients=[sender_email],
                html_body=receipt_html
            )
            logger.info(f"Receipt email sent to {sender_email}")
        except Exception as e:
            logger.warning(f"Failed to send receipt email to {sender_email}: {e}")
            # Don't fail the whole request if receipt email fails
    
    return {
        "success": True,
        "message": f"Documents sent successfully to {len(payload.recipient_emails)} recipient(s)",
        "documents_sent": len(documents),
        "recipients": payload.recipient_emails,
        "receipt_sent": sender_email is not None
    }


@router.get("/email-logs", response_model=List[DocumentEmailLogRead], summary="List document email logs")
def list_document_email_logs(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs to return (1-1000)"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    status: Optional[str] = Query(None, description="Filter by status (sent, failed, partial)"),
    sender_user_id: Optional[str] = Query(None, description="Filter by sender user ID"),
    document_id: Optional[str] = Query(None, description="Filter by document ID (logs containing this document)"),
    start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    List document email logs.
    
    **Permissions:**
    - Regular users: Can only see their own email logs
    - Admin, Super Admin: Can see all email logs
    
    **Filters:**
    - status: Filter by status (sent, failed, partial)
    - sender_user_id: Filter by sender (admin only)
    - document_id: Filter logs containing a specific document
    - start_date/end_date: Filter by date range (ISO format)
    """
    client = get_supabase_client()
    
    # Build query
    query = client.table("document_email_logs").select("*")
    
    # Permission check: regular users can only see their own logs
    if current_user.role not in ["admin", "super_admin"]:
        query = query.eq("sender_user_id", current_user.auth_user_id)
    elif sender_user_id:
        # Admin can filter by specific sender
        query = query.eq("sender_user_id", sender_user_id)
    
    # Apply filters
    if status:
        if status not in ["sent", "failed", "partial"]:
            raise HTTPException(400, "Status must be one of: sent, failed, partial")
        query = query.eq("status", status)
    
    if document_id:
        # Filter logs that contain this document ID in the array
        query = query.contains("document_ids", [document_id])
    
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.gte("sent_at", start_dt.isoformat())
        except Exception:
            raise HTTPException(400, "Invalid start_date format. Use ISO format.")
    
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.lte("sent_at", end_dt.isoformat())
        except Exception:
            raise HTTPException(400, "Invalid end_date format. Use ISO format.")
    
    # Apply pagination and ordering
    query = query.order("sent_at", desc=True).range(offset, offset + limit - 1)
    
    try:
        result = query.execute()
        logs = result.data or []
        
        # Enrich logs with document titles
        enriched_logs = []
        for log in logs:
            document_ids = log.get("document_ids", [])
            document_titles = []
            
            if document_ids:
                # Fetch document titles
                docs_result = (
                    client.table("documents")
                    .select("id, title")
                    .in_("id", document_ids)
                    .execute()
                )
                
                # Create a map of document_id -> title
                doc_map = {doc["id"]: doc.get("title", "Untitled") for doc in (docs_result.data or [])}
                
                # Preserve order and get titles
                for doc_id in document_ids:
                    title = doc_map.get(doc_id, "Unknown Document")
                    document_titles.append(title)
            
            # Add enriched fields
            log["document_titles"] = document_titles
            enriched_logs.append(log)
        
        return enriched_logs
    except Exception as e:
        logger.error(f"Failed to list document email logs: {e}")
        raise HTTPException(500, f"Failed to list email logs: {str(e)}")


@router.get("/email-logs/{log_id}", response_model=DocumentEmailLogRead, summary="Get document email log by ID")
def get_document_email_log(
    log_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get a specific document email log by ID.
    
    **Permissions:**
    - Regular users: Can only see their own email logs
    - Admin, Super Admin: Can see any email log
    """
    client = get_supabase_client()
    
    try:
        result = (
            client.table("document_email_logs")
            .select("*")
            .eq("id", log_id)
            .maybe_single()
            .execute()
        )
        
        if not result.data:
            raise HTTPException(404, "Email log not found")
        
        log = result.data
        
        # Permission check: regular users can only see their own logs
        if current_user.role not in ["admin", "super_admin"]:
            if log.get("sender_user_id") != current_user.auth_user_id:
                raise HTTPException(403, "You do not have access to this email log")
        
        # Enrich with document titles
        document_ids = log.get("document_ids", [])
        document_titles = []
        
        if document_ids:
            docs_result = (
                client.table("documents")
                .select("id, title")
                .in_("id", document_ids)
                .execute()
            )
            
            doc_map = {doc["id"]: doc.get("title", "Untitled") for doc in (docs_result.data or [])}
            
            for doc_id in document_ids:
                title = doc_map.get(doc_id, "Unknown Document")
                document_titles.append(title)
        
        log["document_titles"] = document_titles
        
        return log
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document email log: {e}")
        raise HTTPException(500, f"Failed to get email log: {str(e)}")

