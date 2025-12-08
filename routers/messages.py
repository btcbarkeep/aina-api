# routers/messages.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta

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
    
    **Reply Restrictions:**
    - If replying to a message with `replies_disabled=True`, only admins can reply
    - Regular users will receive a 403 error if trying to reply to a bulk announcement
    
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
                
                # Check if there's a recent message from this recipient with replies_disabled
                # (indicating this might be a reply to a bulk announcement)
                # Look for messages sent in the last 30 days to avoid blocking old conversations
                thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
                
                recent_message_result = (
                    client.table("messages")
                    .select("id, replies_disabled, created_at")
                    .eq("from_user_id", payload.to_user_id)
                    .eq("to_user_id", current_user.auth_user_id)
                    .eq("replies_disabled", True)
                    .gte("created_at", thirty_days_ago)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                
                if recent_message_result.data:
                    raise HTTPException(
                        403,
                        "Replies are disabled for this message. Only admins can reply to bulk announcements."
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
        "replies_disabled": False,  # Regular messages allow replies
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
        # Fetch messages where user is recipient
        recipient_result = (
            client.table("messages")
            .select("*")
            .eq("to_user_id", current_user.auth_user_id)
            .order("created_at", desc=True)
            .execute()
        )
        
        # Fetch messages where user sent to admins (to_user_id is NULL)
        admin_messages_result = (
            client.table("messages")
            .select("*")
            .is_("to_user_id", "null")
            .eq("from_user_id", current_user.auth_user_id)
            .order("created_at", desc=True)
            .execute()
        )
        
        # Combine and deduplicate messages
        recipient_messages = recipient_result.data or []
        admin_messages = admin_messages_result.data or []
        
        # Use a dict to deduplicate by message ID
        messages_dict = {}
        for msg in recipient_messages + admin_messages:
            msg_id = msg.get("id")
            if msg_id and msg_id not in messages_dict:
                messages_dict[msg_id] = msg
        
        # Convert back to list and sort by created_at
        filtered = list(messages_dict.values())
        filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
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
    - 'contractors': Users associated with contractors that have access to AOAO's buildings/units
    - 'property_managers': Users associated with PM companies that have access to AOAO's buildings/units
    - 'owners': Users with role 'owner' that have access to units in AOAO's buildings
    
    **Additional Recipients:**
    - All admins and super_admins automatically receive the message
    
    **Note:**
    - Replies are disabled for bulk messages (only admins can reply)
    - Only users with access to buildings/units that the AOAO manages will receive the message
    """
    # Only AOAO can send bulk messages
    if current_user.role != "aoao":
        raise HTTPException(403, "Only AOAO users can send bulk messages")
    
    if not current_user.aoao_organization_id:
        raise HTTPException(400, "AOAO user must be associated with an AOAO organization to send bulk messages")
    
    # Validate recipient types
    valid_types = ["contractors", "property_managers", "owners"]
    invalid_types = [t for t in payload.recipient_types if t not in valid_types]
    if invalid_types:
        raise HTTPException(400, f"Invalid recipient types: {invalid_types}. Valid types: {valid_types}")
    
    client = get_supabase_client()
    
    try:
        # Get buildings that the AOAO organization has access to
        aoao_buildings_result = (
            client.table("aoao_organization_building_access")
            .select("building_id")
            .eq("aoao_organization_id", current_user.aoao_organization_id)
            .execute()
        )
        aoao_building_ids = [row["building_id"] for row in (aoao_buildings_result.data or [])]
        
        if not aoao_building_ids:
            raise HTTPException(400, "AOAO organization does not have access to any buildings")
        
        # Get all units in these buildings
        units_result = (
            client.table("units")
            .select("id, building_id")
            .in_("building_id", aoao_building_ids)
            .execute()
        )
        aoao_unit_ids = [row["id"] for row in (units_result.data or [])]
        
        # Get users who have access to these buildings/units
        # This includes:
        # - Direct user building access
        # - Direct user unit access
        # - PM companies with building/unit access
        # - Contractors (they have access to all buildings/units)
        
        recipient_ids = set()
        
        # 1. Get all admins and super_admins (always included)
        raw = client.auth.admin.list_users()
        if hasattr(raw, "users"):
            all_users = raw.users
        elif isinstance(raw, list):
            all_users = raw
        elif isinstance(raw, dict) and "users" in raw:
            all_users = raw["users"]
        else:
            all_users = []
        
        for user in all_users:
            if hasattr(user, "id"):
                user_id = user.id
                user_meta = getattr(user, "user_metadata", {}) or {}
            elif isinstance(user, dict):
                user_id = user.get("id")
                user_meta = user.get("user_metadata", {}) or {}
            else:
                continue
            
            user_role = user_meta.get("role", "aoao")
            
            # Always include admins
            if user_role in ["admin", "super_admin"]:
                recipient_ids.add(user_id)
        
        # 2. Get users with direct building access to AOAO's buildings
        # (These will be filtered by recipient type below)
        users_with_building_access = set()
        if aoao_building_ids:
            user_building_access_result = (
                client.table("user_building_access")
                .select("user_id")
                .in_("building_id", aoao_building_ids)
                .execute()
            )
            for row in (user_building_access_result.data or []):
                users_with_building_access.add(row["user_id"])
        
        # 3. Get users with direct unit access to units in AOAO's buildings
        users_with_unit_access = set()
        if aoao_unit_ids:
            user_unit_access_result = (
                client.table("user_unit_access")
                .select("user_id")
                .in_("unit_id", aoao_unit_ids)
                .execute()
            )
            for row in (user_unit_access_result.data or []):
                users_with_unit_access.add(row["user_id"])
        
        # Combine users with access (building or unit)
        users_with_access = users_with_building_access.union(users_with_unit_access)
        
        # 4. Get PM companies with access to AOAO's buildings/units, then get their users
        if aoao_building_ids:
            pm_building_access_result = (
                client.table("pm_company_building_access")
                .select("pm_company_id")
                .in_("building_id", aoao_building_ids)
                .execute()
            )
            pm_company_ids = set([row["pm_company_id"] for row in (pm_building_access_result.data or [])])
            
            if aoao_unit_ids:
                pm_unit_access_result = (
                    client.table("pm_company_unit_access")
                    .select("pm_company_id")
                    .in_("unit_id", aoao_unit_ids)
                    .execute()
                )
                pm_company_ids.update([row["pm_company_id"] for row in (pm_unit_access_result.data or [])])
            
            # Get users associated with these PM companies
            for user in all_users:
                if hasattr(user, "id"):
                    user_id = user.id
                    user_meta = getattr(user, "user_metadata", {}) or {}
                elif isinstance(user, dict):
                    user_id = user.get("id")
                    user_meta = user.get("user_metadata", {}) or {}
                else:
                    continue
                
                pm_company_id = user_meta.get("pm_company_id")
                if pm_company_id and pm_company_id in pm_company_ids:
                    if "property_managers" in payload.recipient_types:
                        recipient_ids.add(user_id)
        
        # 5. Filter users by recipient types and access
        for user in all_users:
            if hasattr(user, "id"):
                user_id = user.id
                user_meta = getattr(user, "user_metadata", {}) or {}
            elif isinstance(user, dict):
                user_id = user.get("id")
                user_meta = user.get("user_metadata", {}) or {}
            else:
                continue
            
            user_role = user_meta.get("role", "aoao")
            contractor_id = user_meta.get("contractor_id")
            pm_company_id = user_meta.get("pm_company_id")
            
            # Skip if user doesn't have access to AOAO's buildings/units (unless admin or contractor)
            has_access = (
                user_id in users_with_access or
                user_role in ["admin", "super_admin"] or
                contractor_id  # Contractors have access to all buildings
            )
            
            if not has_access:
                continue
            
            # Filter by recipient types
            if "contractors" in payload.recipient_types and contractor_id:
                recipient_ids.add(user_id)
            
            if "property_managers" in payload.recipient_types and pm_company_id:
                # Check if PM company has access to AOAO's buildings/units
                if pm_company_id in pm_company_ids:
                    recipient_ids.add(user_id)
            
            if "owners" in payload.recipient_types and user_role == "owner":
                # Owner must have unit access to be included
                if user_id in users_with_unit_access:
                    recipient_ids.add(user_id)
        
        # Remove the sender from recipients
        recipient_ids.discard(current_user.auth_user_id)
        
        if not recipient_ids:
            raise HTTPException(400, f"No eligible recipients found for types: {payload.recipient_types} with access to AOAO's buildings")
        
        # Create messages for all recipients (with replies disabled)
        messages_to_create = []
        for recipient_id in recipient_ids:
            messages_to_create.append({
                "from_user_id": current_user.auth_user_id,
                "to_user_id": recipient_id,
                "subject": payload.subject.strip(),
                "body": payload.body.strip(),
                "is_read": False,
                "replies_disabled": True,  # Disable replies for bulk messages
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

