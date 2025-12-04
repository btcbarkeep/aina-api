# routers/reports.py

from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.permission_helpers import (
    is_admin,
    require_building_access,
    require_unit_access,
    require_event_access,
    require_document_access,
    get_user_accessible_unit_ids,
    get_user_accessible_building_ids,
)
from services.report_generator import (
    generate_building_report,
    generate_unit_report,
    generate_contractor_report,
    generate_custom_report,
    get_effective_role,
    CustomReportFilters,
)

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


# ============================================================
# Request Models
# ============================================================
class CustomReportRequest(BaseModel):
    """Request body for custom report generation."""
    building_id: Optional[str] = None
    unit_ids: Optional[List[str]] = Field(default=[], description="List of unit IDs")
    contractor_ids: Optional[List[str]] = Field(default=[], description="List of contractor IDs")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    include_documents: bool = True
    include_events: bool = True
    format: str = Field(default="json", description="Report format: 'json' or 'pdf'")


# ============================================================
# PUBLIC ENDPOINTS (No Auth Required)
# ============================================================

@router.get(
    "/public/building/{building_id}",
    summary="Generate public building report (AinaReports.com)",
    tags=["Reports - Public"],
)
async def get_public_building_report(
    building_id: str,
    format: str = "json"
):
    """
    Generate a public building report for AinaReports.com.
    No authentication required.
    Returns sanitized data (no internal notes, only public documents).
    """
    try:
        # Validate format
        if format not in ["json", "pdf"]:
            raise HTTPException(400, "format must be 'json' or 'pdf'")
        
        result = await generate_building_report(
            building_id=building_id,
            user=None,
            context_role="public",
            internal=False,
            format=format
        )
        
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to generate building report: {str(e)}")


@router.get(
    "/public/unit/{unit_id}",
    summary="Generate public unit report (AinaReports.com)",
    tags=["Reports - Public"],
)
async def get_public_unit_report(
    unit_id: str,
    format: str = "json"
):
    """
    Generate a public unit report for AinaReports.com.
    No authentication required.
    Returns sanitized data (no internal notes, only public documents).
    """
    try:
        # Validate format
        if format not in ["json", "pdf"]:
            raise HTTPException(400, "format must be 'json' or 'pdf'")
        
        result = await generate_unit_report(
            unit_id=unit_id,
            user=None,
            context_role="public",
            internal=False,
            format=format
        )
        
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to generate unit report: {str(e)}")


# ============================================================
# DASHBOARD ENDPOINTS (Auth Required)
# ============================================================

@router.get(
    "/dashboard/building/{building_id}",
    summary="Generate internal building report (Dashboard)",
    tags=["Reports - Dashboard"],
)
async def get_dashboard_building_report(
    building_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    format: str = "json"
):
    """
    Generate an internal building report for dashboard users.
    Requires authentication.
    Applies role-based visibility rules for events and documents.
    """
    # Permission check: ensure user has access to this building
    if not is_admin(current_user):
        require_building_access(current_user, building_id)
    
    try:
        # Validate format
        if format not in ["json", "pdf"]:
            raise HTTPException(400, "format must be 'json' or 'pdf'")
        
        context_role = get_effective_role(current_user)
        result = await generate_building_report(
            building_id=building_id,
            user=current_user,
            context_role=context_role,
            internal=True,
            format=format
        )
        
        response = result.to_dict()
        response["user_role"] = current_user.role
        return response
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to generate building report: {str(e)}")


@router.get(
    "/dashboard/unit/{unit_id}",
    summary="Generate internal unit report (Dashboard)",
    tags=["Reports - Dashboard"],
)
async def get_dashboard_unit_report(
    unit_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    format: str = "json"
):
    """
    Generate an internal unit report for dashboard users.
    Requires authentication.
    Applies role-based visibility rules for events and documents.
    """
    # Permission check: ensure user has access to this unit
    if not is_admin(current_user):
        require_unit_access(current_user, unit_id)
    
    try:
        # Validate format
        if format not in ["json", "pdf"]:
            raise HTTPException(400, "format must be 'json' or 'pdf'")
        
        context_role = get_effective_role(current_user)
        result = await generate_unit_report(
            unit_id=unit_id,
            user=current_user,
            context_role=context_role,
            internal=True,
            format=format
        )
        
        response = result.to_dict()
        response["user_role"] = current_user.role
        return response
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to generate unit report: {str(e)}")


@router.get(
    "/dashboard/owner/unit/{unit_id}",
    summary="Generate owner-focused unit report (Dashboard)",
    tags=["Reports - Dashboard"],
)
async def get_dashboard_owner_unit_report(
    unit_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    format: str = "json"
):
    """
    Generate an owner-focused unit report.
    Requires authentication and unit ownership.
    Owners can only see contractor_notes (no internal notes).
    """
    # Permission check: ensure user has access to this unit
    if not is_admin(current_user):
        require_unit_access(current_user, unit_id)
    
    # Verify user is an owner (or admin)
    if not is_admin(current_user) and current_user.role != "owner":
        raise HTTPException(403, "Not authorized to generate owner report. Owner role required.")
    
    try:
        # Validate format
        if format not in ["json", "pdf"]:
            raise HTTPException(400, "format must be 'json' or 'pdf'")
        
        # Use "owner" context role for sanitization
        result = await generate_unit_report(
            unit_id=unit_id,
            user=current_user,
            context_role="owner",
            internal=True,
            format=format
        )
        
        response = result.to_dict()
        response["user_role"] = current_user.role
        return response
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to generate owner unit report: {str(e)}")


@router.get(
    "/dashboard/contractor/{contractor_id}",
    summary="Generate contractor activity report (Dashboard)",
    tags=["Reports - Dashboard"],
)
async def get_dashboard_contractor_report(
    contractor_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    format: str = "json"
):
    """
    Generate a contractor activity report.
    Requires authentication.
    
    - Admin/AOAO/PM: Can view any contractor report
    - Contractors: Can only view their own report
    """
    client = get_supabase_client()
    
    # Verify contractor exists
    contractor_result = (
        client.table("contractors")
        .select("id")
        .eq("id", contractor_id)
        .limit(1)
        .execute()
    )
    
    if not contractor_result.data:
        raise HTTPException(404, f"Contractor {contractor_id} not found")
    
    # Permission check: contractors can only view their own report
    if not is_admin(current_user) and current_user.role == "contractor":
        user_contractor_id = getattr(current_user, "contractor_id", None)
        if not user_contractor_id or str(user_contractor_id) != contractor_id:
            raise HTTPException(
                status_code=403,
                detail="You can only view your own contractor report"
            )
    
    try:
        # Validate format
        if format not in ["json", "pdf"]:
            raise HTTPException(400, "format must be 'json' or 'pdf'")
        
        context_role = get_effective_role(current_user)
        
        # For contractors, use "contractor" context role for sanitization
        if current_user.role == "contractor":
            context_role = "contractor"
        
        result = await generate_contractor_report(
            contractor_id=contractor_id,
            user=current_user,
            context_role=context_role,
            format=format
        )
        
        response = result.to_dict()
        response["user_role"] = current_user.role
        return response
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to generate contractor report: {str(e)}")


@router.post(
    "/dashboard/custom",
    summary="Generate custom report (Dashboard)",
    tags=["Reports - Dashboard"],
)
async def post_dashboard_custom_report(
    request: CustomReportRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Generate a custom report based on filters.
    Requires authentication.
    Applies role-based permissions and visibility rules.
    """
    # Validate format
    if request.format not in ["json", "pdf"]:
        raise HTTPException(400, "format must be 'json' or 'pdf'")
    
    # Permission checks based on filters
    if not is_admin(current_user):
        # Check building access if building_id provided
        if request.building_id:
            require_building_access(current_user, request.building_id)
        
        # Check unit access if unit_ids provided
        if request.unit_ids:
            # AOAO roles can access units in their buildings even without explicit unit access
            if current_user.role not in ["aoao", "aoao_staff"]:
                # For each unit, verify access
                for unit_id in request.unit_ids:
                    require_unit_access(current_user, unit_id)
        
        # Contractors can only filter by their own contractor_id
        if request.contractor_ids and current_user.role == "contractor":
            user_contractor_id = getattr(current_user, "contractor_id", None)
            if not user_contractor_id:
                raise HTTPException(
                    status_code=403,
                    detail="Contractor account missing contractor_id"
                )
            # Verify all requested contractor_ids match the user's contractor_id
            user_contractor_id_str = str(user_contractor_id)
            for cid in request.contractor_ids:
                if str(cid) != user_contractor_id_str:
                    raise HTTPException(
                        status_code=403,
                        detail="You can only filter by your own contractor_id"
                    )
    
    try:
        context_role = get_effective_role(current_user)
        
        # For contractors, use "contractor" context role
        if current_user.role == "contractor":
            context_role = "contractor"
        
        filters = CustomReportFilters(
            building_id=request.building_id,
            unit_ids=request.unit_ids or [],
            contractor_ids=request.contractor_ids or [],
            start_date=request.start_date,
            end_date=request.end_date,
            include_documents=request.include_documents,
            include_events=request.include_events,
        )
        
        result = await generate_custom_report(
            filters=filters,
            user=current_user,
            context_role=context_role,
            format=request.format
        )
        
        response = result.to_dict()
        response["user_role"] = current_user.role
        return response
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to generate custom report: {str(e)}")
