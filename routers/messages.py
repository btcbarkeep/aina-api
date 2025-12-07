# routers/messages.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.logging_config import logger
from core.permission_helpers import requires_permission
from models.message import MessageCreate, MessageUpdate, MessageRead

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
    
    If `to_user_id` is None, the message is sent to admins.
    """
    client = get_supabase_client()
    
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
        
        logger.info(f"User {current_user.auth_user_id} sent message to {payload.to_user_id or 'admins'}")
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
        
        query_result = filtered
        
        if unread_only:
            query = query.eq("is_read", False)
        
        result = query.execute()
        return result.data or []
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

