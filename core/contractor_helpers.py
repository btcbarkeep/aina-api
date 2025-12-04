# core/contractor_helpers.py

from typing import Dict, Any
from core.supabase_client import get_supabase_client


def enrich_contractor_with_roles(contractor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add roles array to contractor dict.
    Centralized function to avoid code duplication.
    
    Args:
        contractor: Contractor dictionary with at least an 'id' field
    
    Returns:
        Contractor dictionary with 'roles' array added
    """
    contractor_id = contractor.get("id")
    if not contractor_id:
        contractor["roles"] = []
        return contractor
    
    client = get_supabase_client()
    
    # Get roles for this contractor
    role_result = (
        client.table("contractor_role_assignments")
        .select("role_id, contractor_roles(name)")
        .eq("contractor_id", contractor_id)
        .execute()
    )
    
    roles = []
    if role_result.data:
        for row in role_result.data:
            if row.get("contractor_roles") and row["contractor_roles"].get("name"):
                roles.append(row["contractor_roles"]["name"])
    
    contractor["roles"] = roles
    return contractor

