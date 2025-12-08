# core/batch_helpers.py
# Batch query helpers to prevent N+1 query problems

from typing import Dict, List, Any
from core.supabase_client import get_supabase_client
from core.contractor_helpers import batch_enrich_contractors_with_roles
from core.logging_config import logger


def batch_get_document_relations(document_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Batch fetch units and contractors for multiple documents.
    Returns a dictionary mapping document_id -> {"units": [...], "contractors": [...]}
    
    Args:
        document_ids: List of document IDs
    
    Returns:
        Dictionary mapping document_id to dict with "units" and "contractors" lists
    """
    if not document_ids:
        return {}
    
    client = get_supabase_client()
    
    # Initialize result structure
    result_map: Dict[str, Dict[str, Any]] = {
        doc_id: {"units": [], "contractors": []} for doc_id in document_ids
    }
    
    # Batch fetch all document_units
    document_units_result = (
        client.table("document_units")
        .select("document_id, unit_id, units(*)")
        .in_("document_id", document_ids)
        .execute()
    )
    
    if document_units_result.data:
        for row in document_units_result.data:
            doc_id = row.get("document_id")
            unit = row.get("units")
            if doc_id and unit and doc_id in result_map:
                result_map[doc_id]["units"].append(unit)
    
    # Batch fetch all document_contractors
    document_contractors_result = (
        client.table("document_contractors")
        .select("document_id, contractor_id, contractors(*)")
        .in_("document_id", document_ids)
        .execute()
    )
    
    contractors_list = []
    contractor_doc_map: Dict[str, List[str]] = {}  # contractor_id -> list of doc_ids
    
    if document_contractors_result.data:
        for row in document_contractors_result.data:
            doc_id = row.get("document_id")
            contractor = row.get("contractors")
            if doc_id and contractor and doc_id in result_map:
                contractor_id = contractor.get("id")
                if contractor_id:
                    if contractor_id not in contractor_doc_map:
                        contractor_doc_map[contractor_id] = []
                        contractors_list.append(contractor)
                    contractor_doc_map[contractor_id].append(doc_id)
    
    # Batch enrich all contractors with roles
    if contractors_list:
        enriched_contractors = batch_enrich_contractors_with_roles(contractors_list)
        contractor_map = {c["id"]: c for c in enriched_contractors}
        
        # Map contractors back to documents
        for contractor_id, doc_ids in contractor_doc_map.items():
            contractor = contractor_map.get(contractor_id)
            if contractor:
                for doc_id in doc_ids:
                    if doc_id in result_map:
                        result_map[doc_id]["contractors"].append(contractor)
    
    return result_map


def batch_get_event_relations(event_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Batch fetch units and contractors for multiple events.
    Returns a dictionary mapping event_id -> {"units": [...], "contractors": [...]}
    
    Args:
        event_ids: List of event IDs
    
    Returns:
        Dictionary mapping event_id to dict with "units" and "contractors" lists
    """
    if not event_ids:
        return {}
    
    client = get_supabase_client()
    
    # Initialize result structure
    result_map: Dict[str, Dict[str, Any]] = {
        event_id: {"units": [], "contractors": []} for event_id in event_ids
    }
    
    # Batch fetch all event_units
    event_units_result = (
        client.table("event_units")
        .select("event_id, unit_id, units(*)")
        .in_("event_id", event_ids)
        .execute()
    )
    
    if event_units_result.data:
        for row in event_units_result.data:
            event_id = row.get("event_id")
            unit = row.get("units")
            if event_id and unit and event_id in result_map:
                result_map[event_id]["units"].append(unit)
    
    # Batch fetch all event_contractors
    event_contractors_result = (
        client.table("event_contractors")
        .select("event_id, contractor_id, contractors(*)")
        .in_("event_id", event_ids)
        .execute()
    )
    
    contractors_list = []
    contractor_event_map: Dict[str, List[str]] = {}  # contractor_id -> list of event_ids
    
    if event_contractors_result.data:
        for row in event_contractors_result.data:
            event_id = row.get("event_id")
            contractor = row.get("contractors")
            if event_id and contractor and event_id in result_map:
                contractor_id = contractor.get("id")
                if contractor_id:
                    if contractor_id not in contractor_event_map:
                        contractor_event_map[contractor_id] = []
                        contractors_list.append(contractor)
                    contractor_event_map[contractor_id].append(event_id)
    
    # Batch enrich all contractors with roles
    if contractors_list:
        enriched_contractors = batch_enrich_contractors_with_roles(contractors_list)
        contractor_map = {c["id"]: c for c in enriched_contractors}
        
        # Map contractors back to events
        for contractor_id, event_ids_list in contractor_event_map.items():
            contractor = contractor_map.get(contractor_id)
            if contractor:
                for event_id in event_ids_list:
                    if event_id in result_map:
                        result_map[event_id]["contractors"].append(contractor)
    
    return result_map


def batch_enrich_documents_with_relations(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Batch enrich multiple documents with their units, contractors, and uploader info.
    This is much more efficient than calling enrich_document_with_relations in a loop.
    
    Args:
        documents: List of document dictionaries
    
    Returns:
        List of document dictionaries with "units", "contractors", and uploader info added
    """
    if not documents:
        return documents
    
    # Extract document IDs
    document_ids = [d.get("id") for d in documents if d.get("id")]
    
    if not document_ids:
        # No valid IDs, just add empty arrays
        for doc in documents:
            doc["units"] = []
            doc["contractors"] = []
            doc["unit_ids"] = []
            doc["contractor_ids"] = []
        return documents
    
    # Batch fetch all relations
    relations_map = batch_get_document_relations(document_ids)
    
    # Batch fetch uploader names for all documents (role is already stored in uploaded_by_role)
    uploader_ids = list(set([d.get("uploaded_by") for d in documents if d.get("uploaded_by")]))
    uploader_info_map = {}
    
    if uploader_ids:
        client = get_supabase_client()
        # Fetch user metadata for all uploaders (only need name, role is already in document)
        for user_id in uploader_ids:
            try:
                auth_user = client.auth.admin.get_user_by_id(user_id)
                if auth_user and auth_user.user:
                    user_meta = auth_user.user.user_metadata or {}
                    uploader_info_map[user_id] = {
                        "full_name": user_meta.get("full_name"),
                    }
            except Exception as e:
                # If we can't fetch user info, skip it
                logger.debug(f"Could not fetch uploader name for user {user_id}: {e}")
                pass
    
    # Enrich each document
    for doc in documents:
        doc_id = doc.get("id")
        if doc_id and doc_id in relations_map:
            relations = relations_map[doc_id]
            doc["units"] = relations.get("units", [])
            doc["contractors"] = relations.get("contractors", [])
            doc["unit_ids"] = [u["id"] for u in doc["units"]]
            doc["contractor_ids"] = [c["id"] for c in doc["contractors"]]
        else:
            doc["units"] = []
            doc["contractors"] = []
            doc["unit_ids"] = []
            doc["contractor_ids"] = []
        
        # Add uploader name (role is already stored in uploaded_by_role from database)
        uploaded_by = doc.get("uploaded_by")
        if uploaded_by and uploaded_by in uploader_info_map:
            uploader_info = uploader_info_map[uploaded_by]
            doc["uploaded_by_name"] = uploader_info.get("full_name")
        else:
            doc["uploaded_by_name"] = None
        # Note: uploaded_by_role is already in the document from the database query
    
    return documents


def batch_enrich_events_with_relations(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Batch enrich multiple events with their units and contractors.
    This is much more efficient than calling enrich_event_with_relations in a loop.
    
    Args:
        events: List of event dictionaries
    
    Returns:
        List of event dictionaries with "units" and "contractors" arrays added
    """
    if not events:
        return events
    
    # Extract event IDs
    event_ids = [e.get("id") for e in events if e.get("id")]
    
    if not event_ids:
        # No valid IDs, just add empty arrays
        for event in events:
            event["units"] = []
            event["contractors"] = []
            event["unit_ids"] = []
            event["contractor_ids"] = []
        return events
    
    # Batch fetch all relations
    relations_map = batch_get_event_relations(event_ids)
    
    # Enrich each event
    for event in events:
        event_id = event.get("id")
        if event_id and event_id in relations_map:
            relations = relations_map[event_id]
            event["units"] = relations.get("units", [])
            event["contractors"] = relations.get("contractors", [])
            event["unit_ids"] = [u["id"] for u in event["units"]]
            event["contractor_ids"] = [c["id"] for c in event["contractors"]]
        else:
            event["units"] = []
            event["contractors"] = []
            event["unit_ids"] = []
            event["contractor_ids"] = []
    
    return events

