# core/contractor_helpers.py

from typing import Dict, Any, List
from core.supabase_client import get_supabase_client


def get_contractor_roles(contractor_id: str) -> List[str]:
    """
    Get roles for a single contractor.
    Used for single contractor enrichment.
    """
    client = get_supabase_client()
    result = (
        client.table("contractor_role_assignments")
        .select("role_id, contractor_roles(name)")
        .eq("contractor_id", contractor_id)
        .execute()
    )
    roles = []
    if result.data:
        for row in result.data:
            if row.get("contractor_roles") and row["contractor_roles"].get("name"):
                roles.append(row["contractor_roles"]["name"])
    return roles


def batch_get_contractor_roles(contractor_ids: List[str]) -> Dict[str, List[str]]:
    """
    Batch fetch roles for multiple contractors.
    Returns a dictionary mapping contractor_id -> list of role names.
    
    Args:
        contractor_ids: List of contractor IDs
    
    Returns:
        Dictionary mapping contractor_id to list of role names
    """
    if not contractor_ids:
        return {}
    
    client = get_supabase_client()
    
    # Batch fetch all role assignments for all contractors
    result = (
        client.table("contractor_role_assignments")
        .select("contractor_id, contractor_roles(name)")
        .in_("contractor_id", contractor_ids)
        .execute()
    )
    
    # Build mapping: contractor_id -> list of role names
    contractor_roles_map: Dict[str, List[str]] = {cid: [] for cid in contractor_ids}
    
    if result.data:
        for row in result.data:
            contractor_id = row.get("contractor_id")
            role_name = None
            if row.get("contractor_roles") and row["contractor_roles"].get("name"):
                role_name = row["contractor_roles"]["name"]
            
            if contractor_id and role_name:
                if contractor_id not in contractor_roles_map:
                    contractor_roles_map[contractor_id] = []
                contractor_roles_map[contractor_id].append(role_name)
    
    return contractor_roles_map


def enrich_contractor_with_roles(contractor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add roles array to contractor dict.
    Centralized function to avoid code duplication.
    
    NOTE: For multiple contractors, use batch_enrich_contractors_with_roles instead.
    
    Args:
        contractor: Contractor dictionary with at least an 'id' field
    
    Returns:
        Contractor dictionary with 'roles' array added
    """
    contractor_id = contractor.get("id")
    if not contractor_id:
        contractor["roles"] = []
        return contractor
    
    contractor["roles"] = get_contractor_roles(contractor_id)
    return contractor


def batch_enrich_contractors_with_roles(contractors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Batch enrich multiple contractors with their roles.
    This is much more efficient than calling enrich_contractor_with_roles in a loop.
    
    Args:
        contractors: List of contractor dictionaries
    
    Returns:
        List of contractor dictionaries with 'roles' array added to each
    """
    if not contractors:
        return contractors
    
    # Extract contractor IDs
    contractor_ids = [c.get("id") for c in contractors if c.get("id")]
    
    if not contractor_ids:
        # No valid IDs, just add empty roles
        for contractor in contractors:
            contractor["roles"] = []
        return contractors
    
    # Batch fetch all roles
    roles_map = batch_get_contractor_roles(contractor_ids)
    
    # Enrich each contractor
    for contractor in contractors:
        contractor_id = contractor.get("id")
        if contractor_id:
            contractor["roles"] = roles_map.get(contractor_id, [])
        else:
            contractor["roles"] = []
    
    return contractors

