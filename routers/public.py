# routers/public.py

import re
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
    Mirrors the exact search logic from ainareports.com frontend.
    Designed to replace direct Supabase queries on the frontend.
    
    Returns matching buildings and units in the exact format expected by the frontend.
    
    Query parameter is optional - if not provided or too short (< 2 chars), returns empty results.
    """
    client = get_supabase_client()
    
    # Handle empty or missing query
    if not query or len(query.strip()) < 2:
        return {
            "buildings": [],
            "units": [],
        }
    
    q = query.strip()
    
    # Separate building name words (non-numeric) from unit numbers (numeric)
    query_words = [w for w in q.lower().split() if len(w) > 0]
    building_name_words = [word for word in query_words if not re.search(r'\d', word)]
    unit_number_words = [word for word in query_words if re.search(r'\d', word)]
    has_unit_number = len(unit_number_words) > 0
    has_building_name = len(building_name_words) > 0
    
    buildings = []
    buildings_error = None
    
    # ============================================================
    # BUILDINGS SEARCH
    # ============================================================
    try:
        if has_building_name and has_unit_number:
            # When we have BOTH building name AND unit number:
            # Only match buildings on building name words (ignore numbers in addresses/zip)
            building_conditions = []
            for word in building_name_words:
                building_conditions.append(f"name.ilike.*{word}*")
                building_conditions.append(f"address.ilike.*{word}*")
                building_conditions.append(f"city.ilike.*{word}*")
                building_conditions.append(f"state.ilike.*{word}*")
            
            result = (
                client.table("buildings")
                .select("id, name, address, city, state, zip, slug")
                .or(",".join(building_conditions))
                .limit(10)
                .execute()
            )
            buildings = result.data or []
            buildings_error = result.error
            
        elif has_building_name:
            # Only building name words - prioritize building name matches
            # First, try matching building names only
            name_conditions = [f"name.ilike.*{word}*" for word in building_name_words]
            name_result = (
                client.table("buildings")
                .select("id, name, address, city, state, zip, slug")
                .or(",".join(name_conditions))
                .limit(10)
                .execute()
            )
            
            buildings = name_result.data or []
            buildings_error = name_result.error
            
            # Only search addresses if we got NO results from building names
            # This prevents "Aina" from matching all buildings with "Aina" in addresses
            if len(buildings) == 0 and not buildings_error:
                # Search addresses only (not city/state) to be more precise
                address_conditions = [f"address.ilike.*{word}*" for word in building_name_words]
                
                address_result = (
                    client.table("buildings")
                    .select("id, name, address, city, state, zip, slug")
                    .or(",".join(address_conditions))
                    .limit(20)  # Get more to filter
                    .execute()
                )
                
                if not address_result.error and address_result.data:
                    # Double-check: filter to ensure the word actually appears in the address
                    buildings = [
                        b for b in address_result.data
                        if any(word in (b.get("address") or "").lower() for word in building_name_words)
                    ][:10]
        else:
            # No building name words (only numbers) - match all words
            # But require ALL words to match (not just any word)
            building_conditions = []
            for word in query_words:
                building_conditions.append(f"name.ilike.*{word}*")
                building_conditions.append(f"address.ilike.*{word}*")
                building_conditions.append(f"city.ilike.*{word}*")
                building_conditions.append(f"state.ilike.*{word}*")
                building_conditions.append(f"zip.ilike.*{word}*")
            
            # For multi-word queries, filter results to ensure all words are present
            if len(query_words) > 1:
                result = (
                    client.table("buildings")
                    .select("id, name, address, city, state, zip, slug")
                    .or(",".join(building_conditions))
                    .limit(20)  # Get more results to filter
                    .execute()
                )
                
                if not result.error and result.data:
                    # Filter to only include buildings where ALL words match
                    buildings = [
                        b for b in result.data
                        if all(
                            word in f"{b.get('name', '')} {b.get('address', '')} {b.get('city', '')} {b.get('state', '')} {b.get('zip', '')}".lower()
                            for word in query_words
                        )
                    ][:10]
                else:
                    buildings = []
                    buildings_error = result.error
            else:
                # Single word query - use simple OR
                result = (
                    client.table("buildings")
                    .select("id, name, address, city, state, zip, slug")
                    .or(",".join(building_conditions))
                    .limit(10)
                    .execute()
                )
                buildings = result.data or []
                buildings_error = result.error
                
    except Exception as e:
        print(f"Error searching buildings: {e}")
        buildings_error = e
        buildings = []
    
    if buildings_error:
        print(f"Error fetching buildings: {buildings_error}")
    
    # ============================================================
    # UNITS SEARCH
    # ============================================================
    units = []
    
    # Get matched building IDs to filter out units from other buildings
    matched_building_ids = set(b["id"] for b in buildings) if buildings else set()
    
    # 1) GET UNITS BY BUILDING MATCH (filter by unit number if present)
    if buildings:
        building_ids = list(matched_building_ids)
        
        units_by_building_query = (
            client.table("units")
            .select("id, unit_number, building_id")
            .in_("building_id", building_ids)
        )
        
        # If we have a unit number in the query, filter by it
        if has_unit_number:
            unit_number_conditions = [f"unit_number.ilike.*{word}*" for word in unit_number_words]
            units_by_building_query = units_by_building_query.or(",".join(unit_number_conditions))
        
        units_by_building_result = units_by_building_query.execute()
        
        if units_by_building_result.error:
            print(f"Error fetching units by building: {units_by_building_result.error}")
        elif units_by_building_result.data:
            units.extend(units_by_building_result.data)
    
    # 2) GET UNITS DIRECTLY MATCHING UNIT NUMBER
    # If we have building matches, only include units from those buildings
    if has_unit_number:
        for word in unit_number_words:
            units_by_number_query = (
                client.table("units")
                .select("id, unit_number, building_id")
                .ilike("unit_number", f"%%{word}%%")
            )
            
            # If we have building matches, filter to only those buildings
            if matched_building_ids:
                units_by_number_query = units_by_number_query.in_("building_id", list(matched_building_ids))
            
            units_by_number_result = units_by_number_query.execute()
            
            if not units_by_number_result.error and units_by_number_result.data:
                units.extend(units_by_number_result.data)
    
    # 3) GET UNITS BY BUILDING TEXT (only if no building matches yet)
    # This helps find buildings that weren't found in the initial building search
    # We do this by searching for buildings again with broader criteria, then getting their units
    if not buildings and has_building_name:
        # Search buildings by text again (broader search)
        building_text_conditions = []
        for word in query_words:
            building_text_conditions.append(f"name.ilike.*{word}*")
            building_text_conditions.append(f"address.ilike.*{word}*")
            building_text_conditions.append(f"city.ilike.*{word}*")
            building_text_conditions.append(f"state.ilike.*{word}*")
        
        buildings_by_text_result = (
            client.table("buildings")
            .select("id")
            .or(",".join(building_text_conditions))
            .limit(20)
            .execute()
        )
        
        if buildings_by_text_result.data:
            building_ids_from_text = [b["id"] for b in buildings_by_text_result.data]
            
            # Get units from these buildings
            units_by_building_text_query = (
                client.table("units")
                .select("id, unit_number, building_id")
                .in_("building_id", building_ids_from_text)
            )
            
            # If we have unit numbers, filter by them
            if has_unit_number:
                unit_number_conditions = [f"unit_number.ilike.*{word}*" for word in unit_number_words]
                units_by_building_text_query = units_by_building_text_query.or(",".join(unit_number_conditions))
            
            units_by_building_text_result = units_by_building_text_query.execute()
            
            if not units_by_building_text_result.error and units_by_building_text_result.data:
                units.extend(units_by_building_text_result.data)
    
    # 4) REMOVE DUPLICATES and FETCH BUILDING INFO
    unique_units_dict = {}
    for u in units:
        unique_units_dict[u["id"]] = u
    
    # Fetch building info for all unique units
    if unique_units_dict:
        unit_building_ids = list(set(u.get("building_id") for u in unique_units_dict.values() if u.get("building_id")))
        
        if unit_building_ids:
            buildings_for_units_result = (
                client.table("buildings")
                .select("id, name, slug, address, city, state, zip")
                .in_("id", unit_building_ids)
                .execute()
            )
            
            building_map = {b["id"]: b for b in (buildings_for_units_result.data or [])}
            
            # Combine unit and building info
            units_with_buildings = []
            for unit in unique_units_dict.values():
                building_id = unit.get("building_id")
                building = building_map.get(building_id)
                if building:
                    units_with_buildings.append({
                        "id": unit.get("id"),
                        "unit_number": unit.get("unit_number"),
                        "building_id": building_id,
                        "building": building,
                    })
            
            units = units_with_buildings
        else:
            units = []
    
    return {
        "buildings": buildings or [],
        "units": units,
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
