# routers/requests.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.logging_config import logger
from core.permission_helpers import requires_permission
from models.access_request import AccessRequestCreate, AccessRequestUpdate, AccessRequestRead

router = APIRouter(
    prefix="/requests",
    tags=["Access Requests"],
)


@router.post("/", response_model=AccessRequestRead)
def create_access_request(
    payload: AccessRequestCreate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Create an access request (e.g., PM requesting to manage a building/unit).
    
    Users can request access to buildings or units they don't currently have access to.
    """
    client = get_supabase_client()
    
    # Validate request type and IDs
    if payload.request_type == "building" and not payload.building_id:
        raise HTTPException(400, "building_id is required for building requests")
    if payload.request_type == "unit" and not payload.unit_id:
        raise HTTPException(400, "unit_id is required for unit requests")
    
    # Validate building/unit exists
    if payload.building_id:
        building_result = (
            client.table("buildings")
            .select("id")
            .eq("id", payload.building_id)
            .limit(1)
            .execute()
        )
        if not building_result.data:
            raise HTTPException(404, f"Building {payload.building_id} not found")
    
    if payload.unit_id:
        unit_result = (
            client.table("units")
            .select("id")
            .eq("id", payload.unit_id)
            .limit(1)
            .execute()
        )
        if not unit_result.data:
            raise HTTPException(404, f"Unit {payload.unit_id} not found")
    
    # Determine organization info if applicable
    organization_type = None
    organization_id = None
    
    if current_user.pm_company_id:
        organization_type = "pm_company"
        organization_id = current_user.pm_company_id
    elif current_user.aoao_organization_id:
        organization_type = "aoao_organization"
        organization_id = current_user.aoao_organization_id
    
    request_data = {
        "requester_user_id": current_user.auth_user_id,
        "request_type": payload.request_type,
        "building_id": payload.building_id,
        "unit_id": payload.unit_id,
        "organization_type": organization_type,
        "organization_id": organization_id,
        "notes": payload.notes,
        "status": "pending",
    }
    
    try:
        result = (
            client.table("access_requests")
            .insert(request_data, returning="representation")
            .execute()
        )
        
        logger.info(
            f"User {current_user.auth_user_id} created {payload.request_type} access request "
            f"for {payload.building_id or payload.unit_id}"
        )
        return result.data[0]
    except Exception as e:
        logger.error(f"Failed to create access request: {e}")
        raise HTTPException(500, f"Failed to create access request: {str(e)}")


@router.get("/", response_model=List[AccessRequestRead])
def list_access_requests(
    status: Optional[str] = Query(None, description="Filter by status (pending, approved, rejected)"),
    request_type: Optional[str] = Query(None, description="Filter by request type (building, unit)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    List access requests.
    
    - Regular users: See only their own requests
    - Admins: See all requests
    """
    client = get_supabase_client()
    
    try:
        if current_user.role in ["admin", "super_admin"]:
            # Admins see all requests
            query = client.table("access_requests").select("*")
        else:
            # Regular users see only their own requests
            query = (
                client.table("access_requests")
                .select("*")
                .eq("requester_user_id", current_user.auth_user_id)
            )
        
        if status:
            query = query.eq("status", status)
        if request_type:
            query = query.eq("request_type", request_type)
        
        result = query.order("created_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to list access requests: {e}")
        raise HTTPException(500, f"Failed to list access requests: {str(e)}")


@router.get("/{request_id}", response_model=AccessRequestRead)
def get_access_request(
    request_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get a specific access request."""
    client = get_supabase_client()
    
    try:
        result = (
            client.table("access_requests")
            .select("*")
            .eq("id", request_id)
            .maybe_single()
            .execute()
        )
        
        if not result.data:
            raise HTTPException(404, "Access request not found")
        
        request_data = result.data
        
        # Check if user has access (requester or admin)
        is_requester = request_data["requester_user_id"] == current_user.auth_user_id
        is_admin = current_user.role in ["admin", "super_admin"]
        
        if not (is_requester or is_admin):
            raise HTTPException(403, "You do not have access to this request")
        
        return request_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get access request: {e}")
        raise HTTPException(500, f"Failed to get access request: {str(e)}")


@router.patch("/{request_id}", response_model=AccessRequestRead)
def update_access_request(
    request_id: str,
    payload: AccessRequestUpdate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Update an access request (admin only).
    
    Admins can approve or reject requests and add admin notes.
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can update access requests")
    
    client = get_supabase_client()
    
    try:
        # Get existing request
        existing = get_access_request(request_id, current_user)
        
        update_data = {}
        
        if payload.status is not None:
            if payload.status not in ["pending", "approved", "rejected"]:
                raise HTTPException(400, "Invalid status. Must be 'pending', 'approved', or 'rejected'")
            update_data["status"] = payload.status
            
            # Set reviewed_by and reviewed_at when status changes
            if payload.status in ["approved", "rejected"]:
                update_data["reviewed_by"] = current_user.auth_user_id
                update_data["reviewed_at"] = datetime.utcnow().isoformat()
        
        if payload.admin_notes is not None:
            update_data["admin_notes"] = payload.admin_notes
        
        if not update_data:
            return existing
        
        result = (
            client.table("access_requests")
            .update(update_data)
            .eq("id", request_id)
            .execute()
        )
        
        if not result.data:
            raise HTTPException(404, "Access request not found")
        
        updated_request = result.data[0]
        
        # If approved, grant the requested access
        if payload.status == "approved":
            try:
                if updated_request["request_type"] == "building":
                    # Grant building access to the organization
                    if updated_request["organization_type"] == "pm_company":
                        # Check if access already exists
                        existing_access = (
                            client.table("pm_company_building_access")
                            .select("id")
                            .eq("pm_company_id", updated_request["organization_id"])
                            .eq("building_id", updated_request["building_id"])
                            .limit(1)
                            .execute()
                        )
                        if not existing_access.data:
                            (
                                client.table("pm_company_building_access")
                                .insert({
                                    "pm_company_id": updated_request["organization_id"],
                                    "building_id": updated_request["building_id"]
                                })
                                .execute()
                            )
                            logger.info(f"Granted building {updated_request['building_id']} access to PM company {updated_request['organization_id']}")
                    elif updated_request["organization_type"] == "aoao_organization":
                        existing_access = (
                            client.table("aoao_organization_building_access")
                            .select("id")
                            .eq("aoao_organization_id", updated_request["organization_id"])
                            .eq("building_id", updated_request["building_id"])
                            .limit(1)
                            .execute()
                        )
                        if not existing_access.data:
                            (
                                client.table("aoao_organization_building_access")
                                .insert({
                                    "aoao_organization_id": updated_request["organization_id"],
                                    "building_id": updated_request["building_id"]
                                })
                                .execute()
                            )
                            logger.info(f"Granted building {updated_request['building_id']} access to AOAO organization {updated_request['organization_id']}")
                
                elif updated_request["request_type"] == "unit":
                    # Grant unit access to the organization
                    if updated_request["organization_type"] == "pm_company":
                        existing_access = (
                            client.table("pm_company_unit_access")
                            .select("id")
                            .eq("pm_company_id", updated_request["organization_id"])
                            .eq("unit_id", updated_request["unit_id"])
                            .limit(1)
                            .execute()
                        )
                        if not existing_access.data:
                            (
                                client.table("pm_company_unit_access")
                                .insert({
                                    "pm_company_id": updated_request["organization_id"],
                                    "unit_id": updated_request["unit_id"]
                                })
                                .execute()
                            )
                            logger.info(f"Granted unit {updated_request['unit_id']} access to PM company {updated_request['organization_id']}")
                    elif updated_request["organization_type"] == "aoao_organization":
                        existing_access = (
                            client.table("aoao_organization_unit_access")
                            .select("id")
                            .eq("aoao_organization_id", updated_request["organization_id"])
                            .eq("unit_id", updated_request["unit_id"])
                            .limit(1)
                            .execute()
                        )
                        if not existing_access.data:
                            (
                                client.table("aoao_organization_unit_access")
                                .insert({
                                    "aoao_organization_id": updated_request["organization_id"],
                                    "unit_id": updated_request["unit_id"]
                                })
                                .execute()
                            )
                            logger.info(f"Granted unit {updated_request['unit_id']} access to AOAO organization {updated_request['organization_id']}")
            except Exception as e:
                logger.error(f"Failed to grant access after approval: {e}")
                # Don't fail the request update, just log the error
        
        logger.info(f"Admin {current_user.auth_user_id} updated access request {request_id} to status {payload.status}")
        return updated_request
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update access request: {e}")
        raise HTTPException(500, f"Failed to update access request: {str(e)}")


@router.delete("/{request_id}")
def delete_access_request(
    request_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete an access request (only requester or admin)."""
    client = get_supabase_client()
    
    try:
        # Get existing request to check permissions
        existing = get_access_request(request_id, current_user)
        
        # Only requester or admin can delete
        is_requester = existing["requester_user_id"] == current_user.auth_user_id
        is_admin = current_user.role in ["admin", "super_admin"]
        
        if not (is_requester or is_admin):
            raise HTTPException(403, "You do not have permission to delete this request")
        
        (
            client.table("access_requests")
            .delete()
            .eq("id", request_id)
            .execute()
        )
        
        logger.info(f"User {current_user.auth_user_id} deleted access request {request_id}")
        return {"status": "deleted", "request_id": request_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete access request: {e}")
        raise HTTPException(500, f"Failed to delete access request: {str(e)}")

