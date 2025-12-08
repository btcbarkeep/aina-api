# routers/public.py

from fastapi import APIRouter, HTTPException
from typing import Optional

from core.supabase_client import get_supabase_client
from services.report_generator import (
    generate_building_report,
    generate_unit_report,
)

router = APIRouter(
    prefix="/reports/public",
    tags=["Reports - Public"],
)


# ============================================================
# GET — Public Search
# ============================================================
@router.get(
    "/search",
    summary="Search buildings, units, and addresses (public)",
)
def search_public(query: Optional[str] = None):
    """
    Public search endpoint for buildings, units, and addresses.
    Designed for autocomplete/autopopulate functionality on AinaReports.com.
    Searches across:
    - Building names
    - Building addresses
    - Unit numbers (combined with building info)
    - Cities and states
    
    Returns matching buildings and units that can be accessed via the public endpoints.
    
    Query parameter is optional - if not provided or too short (< 2 chars), returns empty results.
    """
    client = get_supabase_client()
    
    # Handle empty or missing query
    if not query or len(query.strip()) < 2:
        return {
            "success": True,
            "query": query or "",
            "buildings": [],
            "units": [],
        }
    
    search_term = query.strip()
    results = {
        "buildings": [],
        "units": [],
    }
    
    # Search buildings by name, address, city, state
    try:
        all_buildings = {}
        building_ids_seen = set()
        
        # Search by name
        try:
            name_results = (
                client.table("buildings")
                .select("id, name, address, city, state, zip, slug")
                .ilike("name", f"%{search_term}%")
                .limit(20)
                .execute()
            ).data or []
            for b in name_results:
                if b["id"] not in building_ids_seen:
                    all_buildings[b["id"]] = b
                    building_ids_seen.add(b["id"])
        except Exception:
            pass
        
        # Search by address
        try:
            address_results = (
                client.table("buildings")
                .select("id, name, address, city, state, zip, slug")
                .ilike("address", f"%{search_term}%")
                .limit(20)
                .execute()
            ).data or []
            for b in address_results:
                if b["id"] not in building_ids_seen:
                    all_buildings[b["id"]] = b
                    building_ids_seen.add(b["id"])
        except Exception:
            pass
        
        # Search by city
        try:
            city_results = (
                client.table("buildings")
                .select("id, name, address, city, state, zip, slug")
                .ilike("city", f"%{search_term}%")
                .limit(20)
                .execute()
            ).data or []
            for b in city_results:
                if b["id"] not in building_ids_seen:
                    all_buildings[b["id"]] = b
                    building_ids_seen.add(b["id"])
        except Exception:
            pass
        
        # Search by state
        try:
            state_results = (
                client.table("buildings")
                .select("id, name, address, city, state, zip, slug")
                .ilike("state", f"%{search_term}%")
                .limit(20)
                .execute()
            ).data or []
            for b in state_results:
                if b["id"] not in building_ids_seen:
                    all_buildings[b["id"]] = b
                    building_ids_seen.add(b["id"])
        except Exception:
            pass
        
        results["buildings"] = list(all_buildings.values())[:20]
    except Exception as e:
        print(f"Error searching buildings: {e}")
        results["buildings"] = []
    
    # Search units by unit_number (and include building info)
    try:
        # First, try to find units by unit_number
        units_query = (
            client.table("units")
            .select("id, unit_number, floor, building_id, owner_name")
            .ilike("unit_number", f"%{search_term}%")
            .limit(20)
            .execute()
        )
        
        if units_query.data:
            # Get building info for these units
            building_ids = list(set(u.get("building_id") for u in units_query.data if u.get("building_id")))
            
            if building_ids:
                buildings_for_units = (
                    client.table("buildings")
                    .select("id, name, address, city, state, zip, slug")
                    .in_("id", building_ids)
                    .execute()
                ).data or []
                
                building_map = {b["id"]: b for b in buildings_for_units}
                
                # Combine unit and building info
                for unit in units_query.data:
                    building_id = unit.get("building_id")
                    building = building_map.get(building_id)
                    if building:
                        results["units"].append({
                            **unit,
                            "building": building,
                        })
    except Exception as e:
        print(f"Error searching units: {e}")
        results["units"] = []
    
    return {
        "success": True,
        "query": query,
        "buildings": results["buildings"],
        "units": results["units"],
    }


# ============================================================
# GET — Public Building Report
# ============================================================
@router.get(
    "/building/{building_id}",
    summary="Get public building report (AinaReports.com)",
)
async def get_public_building_report(building_id: str, format: str = "json"):
    """
    Public endpoint to get all public data for a building.
    Used when a user clicks a building from the main search on AinaReports.com.
    
    Returns sanitized data (no internal notes, only public documents) with:
    - Building information
    - Units
    - Events (sanitized for public)
    - Documents (public only)
    - Contractors (with event counts)
    - Property managers (with event counts)
    - AOAO organizations (with event counts)
    - Statistics
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


# ============================================================
# GET — Public Unit Report
# ============================================================
@router.get(
    "/unit/{unit_id}",
    summary="Get public unit report (AinaReports.com)",
)
async def get_public_unit_report(unit_id: str, format: str = "json"):
    """
    Public endpoint to get all public data for a unit.
    Used when a user clicks a specific unit from the main search on AinaReports.com.
    
    Returns sanitized data (no internal notes, only public documents) with:
    - Unit information
    - Building information
    - Events (sanitized for public)
    - Documents (public only)
    - Contractors (with event counts)
    - Property managers (with event counts)
    - AOAO organizations (with event counts)
    - Statistics
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
