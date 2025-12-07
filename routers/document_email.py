# routers/document_email.py

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.logging_config import logger
from core.notifications import send_email
from core.s3_client import get_s3
from models.document_email import DocumentEmailRequest
from core.permission_helpers import require_document_access
from core.role_subscriptions import check_user_has_active_subscription

router = APIRouter(
    prefix="/documents",
    tags=["Document Email"],
)

# Presigned URL expiration for email links (7 days)
EMAIL_PRESIGNED_URL_EXPIRY_SECONDS = 604800  # 7 days


@router.post("/send-email", summary="Send documents via email")
def send_documents_email(
    payload: DocumentEmailRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Send multiple documents (up to 5) via email to multiple recipients.
    
    **Permissions:**
    - AOAO, admin, super_admin: Can always send
    - Property Manager, Owner, Contractor: Must have active paid subscription
    
    **Features:**
    - Sends documents as email attachments (if S3 files) or download links
    - Sends to multiple recipients (email addresses entered by sender)
    - Sends receipt/confirmation email to sender
    - Generates presigned URLs valid for 7 days
    """
    # Check if user has permission to send documents
    allowed_roles = ["aoao", "admin", "super_admin"]
    
    if current_user.role not in allowed_roles:
        # For property_manager, owner, contractor - check if they have active paid subscription
        if current_user.role in ["property_manager", "owner", "contractor"]:
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
This email was sent on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
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
        This email was sent on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small></p>
    </body>
    </html>
    """
    
    # Send email to recipients
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
        raise HTTPException(500, f"Failed to send email: {str(e)}")
    
    # Send receipt/confirmation email to sender
    sender_email = current_user.email
    if sender_email:
        receipt_body = f"""Aloha {current_user.full_name or 'User'},

This is a confirmation that you successfully sent {len(documents)} document(s) via Aina Protocol.

Recipients:
{chr(10).join(payload.recipient_emails)}

Documents sent:
{chr(10).join([f"- {doc.get('title', 'Untitled')}" for doc in documents])}

Sent on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

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
            <p><small>Sent on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small></p>
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

