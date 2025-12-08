# routers/messages.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.logging_config import logger
from core.permission_helpers import requires_permission
from models.message import MessageCreate, MessageUpdate, MessageRead, BulkMessageCreate

router = APIRouter(
    prefix="/messages",
    tags=["Messages"],
)


@router.post("/", response_model=MessageRead)
def send_message(
    payload: MessageCreate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Send a message to another user or to admins.
    
    **Permissions:**
    - Admin/Super Admin: Can message any user (or set to_user_id=None to send to all admins)
    - Regular users: Can only message admins (to_user_id must be None or an admin user ID)
    
    If `to_user_id` is None, the message is sent to admins.
    """
    client = get_supabase_client()
    
    # Validation: Non-admin users can only message admins
    is_admin = current_user.role in ["admin", "super_admin"]
    
    if not is_admin and payload.to_user_id is not None:
        # Regular user trying to message a specific user - verify it's an admin
        try:
            recipient = client.auth.admin.get_user_by_id(payload.to_user_id)
            if recipient.user:
                recipient_meta = recipient.user.user_metadata or {}
                recipient_role = recipient_meta.get("role")
                if recipient_role not in ["admin", "super_admin"]:
                    raise HTTPException(
                        403,
                        "Regular users can only message admins. Set to_user_id to None to message all admins."
                    )
            else:
                raise HTTPException(404, "Recipient user not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to validate recipient: {e}")
            raise HTTPException(400, f"Invalid recipient: {str(e)}")
    
    message_data = {
        "from_user_id": current_user.auth_user_id,
        "to_user_id": payload.to_user_id,  # None = admin message
        "subject": payload.subject.strip(),
        "body": payload.body.strip(),
        "is_read": False,
    }
    
    try:
        result = (
            client.table("messages")
            .insert(message_data, returning="representation")
            .execute()
        )
        
        logger.info(f"User {current_user.auth_user_id} ({current_user.role}) sent message to {payload.to_user_id or 'admins'}")
        return result.data[0]
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        raise HTTPException(500, f"Failed to send message: {str(e)}")


@router.get("/", response_model=List[MessageRead])
def list_messages(
    unread_only: bool = Query(False, description="Filter to unread messages only"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    List messages for the current user.
    
    Returns messages where:
    - User is the recipient (to_user_id matches)
    - OR user sent a message to admins (to_user_id is NULL and from_user_id matches)
    """
    client = get_supabase_client()
    
    try:
        # Get messages where user is recipient OR user sent to admins
        result = (
            client.table("messages")
            .select("*")
            .or_(f"to_user_id.eq.{current_user.auth_user_id},and(to_user_id.is.null,from_user_id.eq.{current_user.auth_user_id})")
            .order("created_at", desc=True)
            .execute()
        )
        
        # Filter in Python for better compatibility
        messages = result.data or []
        filtered = []
        for msg in messages:
            is_recipient = msg.get("to_user_id") == current_user.auth_user_id
            is_sender_to_admins = msg.get("to_user_id") is None and msg.get("from_user_id") == current_user.auth_user_id
            if is_recipient or is_sender_to_admins:
                filtered.append(msg)
        
        # Apply unread filter if requested
        if unread_only:
            filtered = [msg for msg in filtered if not msg.get("is_read", False)]
        
        return filtered
    except Exception as e:
        logger.error(f"Failed to list messages: {e}")
        raise HTTPException(500, f"Failed to list messages: {str(e)}")


@router.get("/sent", response_model=List[MessageRead])
def list_sent_messages(
    current_user: CurrentUser = Depends(get_current_user)
):
    """List messages sent by the current user."""
    client = get_supabase_client()
    
    try:
        result = (
            client.table("messages")
            .select("*")
            .eq("from_user_id", current_user.auth_user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to list sent messages: {e}")
        raise HTTPException(500, f"Failed to list sent messages: {str(e)}")


@router.get("/admin", response_model=List[MessageRead])
def list_admin_messages(
    unread_only: bool = Query(False, description="Filter to unread messages only"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    List all messages sent to admins (admin only).
    
    Returns messages where to_user_id is NULL (admin messages).
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can view admin messages")
    
    client = get_supabase_client()
    
    try:
        query = (
            client.table("messages")
            .select("*")
            .is_("to_user_id", "null")
            .order("created_at", desc=True)
        )
        
        if unread_only:
            query = query.eq("is_read", False)
        
        result = query.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to list admin messages: {e}")
        raise HTTPException(500, f"Failed to list admin messages: {str(e)}")


@router.get("/{message_id}", response_model=MessageRead)
def get_message(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get a specific message (only if user is sender or recipient)."""
    client = get_supabase_client()
    
    try:
        result = (
            client.table("messages")
            .select("*")
            .eq("id", message_id)
            .maybe_single()
            .execute()
        )
        
        if not result.data:
            raise HTTPException(404, "Message not found")
        
        message = result.data
        
        # Check if user is sender, recipient, or admin
        is_sender = message["from_user_id"] == current_user.auth_user_id
        is_recipient = message["to_user_id"] == current_user.auth_user_id
        is_admin_message = message["to_user_id"] is None and current_user.role in ["admin", "super_admin"]
        
        if not (is_sender or is_recipient or is_admin_message):
            raise HTTPException(403, "You do not have access to this message")
        
        return message
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get message: {e}")
        raise HTTPException(500, f"Failed to get message: {str(e)}")


@router.patch("/{message_id}/read", response_model=MessageRead)
def mark_message_read(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Mark a message as read."""
    client = get_supabase_client()
    
    try:
        # First verify user has access to this message
        message = get_message(message_id, current_user)
        
        # Only mark as read if user is the recipient
        if message["to_user_id"] != current_user.auth_user_id and not (message["to_user_id"] is None and current_user.role in ["admin", "super_admin"]):
            raise HTTPException(403, "Only the recipient can mark a message as read")
        
        if message["is_read"]:
            return message  # Already read
        
        result = (
            client.table("messages")
            .update({
                "is_read": True,
                "read_at": datetime.utcnow().isoformat()
            })
            .eq("id", message_id)
            .execute()
        )
        
        if not result.data:
            raise HTTPException(404, "Message not found")
        
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to mark message as read: {e}")
        raise HTTPException(500, f"Failed to mark message as read: {str(e)}")


@router.delete("/{message_id}")
def delete_message(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete a message (only if user is sender)."""
    client = get_supabase_client()
    
    try:
        # First verify user is the sender
        result = (
            client.table("messages")
            .select("from_user_id")
            .eq("id", message_id)
            .maybe_single()
            .execute()
        )
        
        if not result.data:
            raise HTTPException(404, "Message not found")
        
        if result.data["from_user_id"] != current_user.auth_user_id:
            raise HTTPException(403, "Only the sender can delete a message")
        
        (
            client.table("messages")
            .delete()
            .eq("id", message_id)
            .execute()
        )
        
        logger.info(f"User {current_user.auth_user_id} deleted message {message_id}")
        return {"status": "deleted", "message_id": message_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")
        raise HTTPException(500, f"Failed to delete message: {str(e)}")


@router.get("/eligible-recipients")
def get_eligible_recipients(
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get list of users that the current user can message.
    
    **Permissions:**
    - Admin/Super Admin: Can see all users
    - Regular users: Can only see admins
    """
    client = get_supabase_client()
    
    try:
        # Fetch all users
        raw = client.auth.admin.list_users()
        
        # Extract user list (handle different response formats)
        if hasattr(raw, "users"):
            all_users = raw.users
        elif isinstance(raw, list):
            all_users = raw
        elif isinstance(raw, dict) and "users" in raw:
            all_users = raw["users"]
        else:
            all_users = []
        
        is_admin = current_user.role in ["admin", "super_admin"]
        
        eligible = []
        for user in all_users:
            # Extract user data
            if hasattr(user, "id"):
                user_id = user.id
                email = getattr(user, "email", None)
                user_meta = getattr(user, "user_metadata", {}) or {}
            elif isinstance(user, dict):
                user_id = user.get("id")
                email = user.get("email")
                user_meta = user.get("user_metadata", {}) or {}
            else:
                continue
            
            user_role = user_meta.get("role", "aoao")
            full_name = user_meta.get("full_name")
            
            # Filter based on permissions
            if is_admin:
                # Admins can message anyone (except themselves)
                if user_id != current_user.auth_user_id:
                    eligible.append({
                        "id": user_id,
                        "email": email,
                        "full_name": full_name,
                        "role": user_role,
                    })
            else:
                # Regular users can only message admins
                if user_role in ["admin", "super_admin"] and user_id != current_user.auth_user_id:
                    eligible.append({
                        "id": user_id,
                        "email": email,
                        "full_name": full_name,
                        "role": user_role,
                    })
        
        # Sort by full_name or email
        eligible.sort(key=lambda x: (x.get("full_name") or x.get("email") or "").lower())
        
        return {
            "eligible_recipients": eligible,
            "count": len(eligible)
        }
    except Exception as e:
        logger.error(f"Failed to get eligible recipients: {e}")
        raise HTTPException(500, f"Failed to get eligible recipients: {str(e)}")


@router.post("/bulk")
def send_bulk_message(
    payload: BulkMessageCreate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Send a bulk message to multiple users (AOAO only).
    
    **Permissions:**
    - Only AOAO users can send bulk messages
    
    **Recipient Types:**
    - 'contractors': All users associated with contractors
    - 'property_managers': All users associated with property management companies
    - 'owners': All users with role 'owner'
    
    Creates one message record per recipient.
    """
    # Only AOAO can send bulk messages
    if current_user.role != "aoao":
        raise HTTPException(403, "Only AOAO users can send bulk messages")
    
    # Validate recipient types
    valid_types = ["contractors", "property_managers", "owners"]
    invalid_types = [t for t in payload.recipient_types if t not in valid_types]
    if invalid_types:
        raise HTTPException(400, f"Invalid recipient types: {invalid_types}. Valid types: {valid_types}")
    
    client = get_supabase_client()
    
    try:
        # Fetch all users
        raw = client.auth.admin.list_users()
        
        # Extract user list
        if hasattr(raw, "users"):
            all_users = raw.users
        elif isinstance(raw, list):
            all_users = raw
        elif isinstance(raw, dict) and "users" in raw:
            all_users = raw["users"]
        else:
            all_users = []
        
        recipient_ids = set()
        
        # Collect recipients based on types
        for user in all_users:
            # Extract user data
            if hasattr(user, "id"):
                user_id = user.id
                user_meta = getattr(user, "user_metadata", {}) or {}
            elif isinstance(user, dict):
                user_id = user.get("id")
                user_meta = user.get("user_metadata", {}) or {}
            else:
                continue
            
            user_role = user_meta.get("role", "aoao")
            
            # Check if user matches any recipient type
            if "owners" in payload.recipient_types and user_role == "owner":
                recipient_ids.add(user_id)
            
            if "contractors" in payload.recipient_types and user_meta.get("contractor_id"):
                recipient_ids.add(user_id)
            
            if "property_managers" in payload.recipient_types and user_meta.get("pm_company_id"):
                recipient_ids.add(user_id)
        
        if not recipient_ids:
            raise HTTPException(400, f"No recipients found for types: {payload.recipient_types}")
        
        # Create messages for all recipients
        messages_to_create = []
        for recipient_id in recipient_ids:
            messages_to_create.append({
                "from_user_id": current_user.auth_user_id,
                "to_user_id": recipient_id,
                "subject": payload.subject.strip(),
                "body": payload.body.strip(),
                "is_read": False,
            })
        
        # Batch insert messages (Supabase supports batch inserts)
        created_count = 0
        errors = []
        
        # Insert in batches of 100 (Supabase limit)
        batch_size = 100
        for i in range(0, len(messages_to_create), batch_size):
            batch = messages_to_create[i:i + batch_size]
            try:
                result = (
                    client.table("messages")
                    .insert(batch)
                    .execute()
                )
                created_count += len(result.data or [])
            except Exception as e:
                logger.error(f"Failed to insert batch {i//batch_size + 1}: {e}")
                errors.append(f"Batch {i//batch_size + 1}: {str(e)}")
        
        logger.info(
            f"AOAO user {current_user.auth_user_id} sent bulk message to {created_count} recipients "
            f"(types: {payload.recipient_types})"
        )
        
        return {
            "success": True,
            "message": f"Bulk message sent to {created_count} recipients",
            "recipient_count": created_count,
            "recipient_types": payload.recipient_types,
            "errors": errors if errors else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send bulk message: {e}")
        raise HTTPException(500, f"Failed to send bulk message: {str(e)}")

