# services/report_generator.py

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from uuid import uuid4
import uuid
import os
import boto3
from io import BytesIO

from core.supabase_client import get_supabase_client
from core.permission_helpers import (
    is_admin,
    get_user_accessible_unit_ids,
    get_user_accessible_building_ids,
)
from dependencies.auth import CurrentUser


# ============================================================
# Type Definitions
# ============================================================
class ReportResult:
    """Result structure for report generation."""
    def __init__(
        self,
        report_id: str,
        filename: str,
        download_url: Optional[str],
        expires_at: str,
        size_bytes: int,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.report_id = report_id
        self.filename = filename
        self.download_url = download_url
        self.expires_at = expires_at
        self.size_bytes = size_bytes
        self.data = data

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "report_id": self.report_id,
            "filename": self.filename,
            "download_url": self.download_url,
            "expires_at": self.expires_at,
            "size_bytes": self.size_bytes,
        }
        if self.data is not None:
            result["data"] = self.data
        return result


class UploadResult:
    """Result structure for S3 upload."""
    def __init__(self, s3_key: str, download_url: str):
        self.s3_key = s3_key
        self.download_url = download_url


class CustomReportFilters:
    """Filters for custom report generation."""
    def __init__(
        self,
        building_id: Optional[str] = None,
        unit_ids: Optional[List[str]] = None,
        contractor_ids: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_documents: bool = True,
        include_events: bool = True,
    ):
        self.building_id = building_id
        self.unit_ids = unit_ids or []
        self.contractor_ids = contractor_ids or []
        self.start_date = start_date
        self.end_date = end_date
        self.include_documents = include_documents
        self.include_events = include_events


# ============================================================
# Helper — Get effective role
# ============================================================
def get_effective_role(user: Optional[CurrentUser]) -> str:
    """Get the effective role for a user, or 'public' if no user."""
    if not user:
        return "public"
    
    if user.role in ["admin", "super_admin"]:
        return "admin"
    
    return user.role or "public"


# ============================================================
# Helper — Sanitize event for role
# ============================================================
def sanitize_event_for_role(event: Dict[str, Any], role: str) -> Dict[str, Any]:
    """
    Sanitize event based on role visibility rules.
    
    Rules:
    - public: No notes, no owner info
    - owner: contractor_notes only, no internal notes
    - contractor: contractor_notes only, no owner info, no internal notes
    - property_manager: contractor_notes, pm_notes (no aoao_notes, admin_notes)
    - aoao: contractor_notes, pm_notes, aoao_notes (no admin_notes)
    - admin: All notes
    """
    sanitized = event.copy()
    
    if role == "public":
        # Public: Remove all notes and owner info
        sanitized.pop("contractor_notes", None)
        sanitized.pop("pm_notes", None)
        sanitized.pop("aoao_notes", None)
        sanitized.pop("admin_notes", None)
        # Remove owner-related fields if they exist
        sanitized.pop("owner_name", None)
        sanitized.pop("owner_email", None)
        sanitized.pop("owner_phone", None)
    elif role == "owner":
        # Owner: Only contractor_notes
        sanitized.pop("pm_notes", None)
        sanitized.pop("aoao_notes", None)
        sanitized.pop("admin_notes", None)
    elif role == "contractor":
        # Contractor: Only contractor_notes, no owner info
        sanitized.pop("pm_notes", None)
        sanitized.pop("aoao_notes", None)
        sanitized.pop("admin_notes", None)
        # Remove owner-related fields
        sanitized.pop("owner_name", None)
        sanitized.pop("owner_email", None)
        sanitized.pop("owner_phone", None)
    elif role == "property_manager":
        # Property Manager: contractor_notes, pm_notes
        sanitized.pop("aoao_notes", None)
        sanitized.pop("admin_notes", None)
    elif role == "aoao":
        # AOAO: contractor_notes, pm_notes, aoao_notes
        sanitized.pop("admin_notes", None)
    # admin role: Keep all notes (no sanitization needed)
    
    return sanitized


# ============================================================
# Helper — Sanitize document for role
# ============================================================
def sanitize_document_for_role(document: Dict[str, Any], role: str) -> Dict[str, Any]:
    """
    Sanitize document based on role visibility rules.
    
    Rules:
    - public: Only public documents (is_public=True), no sensitive info
    - owner: Documents linked to their unit, no AOAO/PM/Admin-private docs
    - contractor: Documents linked to their events, no owner info
    - property_manager: Documents they have access to
    - aoao: Documents in their buildings
    - admin: All documents
    """
    sanitized = document.copy()
    
    if role == "public":
        # Public: Only public documents, remove sensitive info
        if not sanitized.get("is_public", False):
            return None  # Filter out private documents
        # Remove any sensitive fields
        sanitized.pop("owner_name", None)
        sanitized.pop("owner_email", None)
        sanitized.pop("owner_phone", None)
    elif role == "contractor":
        # Contractor: Remove owner info
        sanitized.pop("owner_name", None)
        sanitized.pop("owner_email", None)
        sanitized.pop("owner_phone", None)
    
    # TODO: Add document_category or is_private flag filtering for owner/PM/AOAO
    # For now, we rely on permission checks to filter documents
    
    return sanitized


# ============================================================
# Helper — Get S3 client (using centralized utility)
# ============================================================
from core.s3_client import get_s3

# ============================================================
# Constants
# ============================================================
REPORT_PRESIGNED_URL_EXPIRY_SECONDS = 604800  # 7 days


# ============================================================
# Helper — Upload report to S3
# ============================================================
async def upload_report_to_s3(file_bytes: bytes, filename: str) -> UploadResult:
    """
    Upload report file to S3 and return download URL.
    Reuses existing S3 upload pattern from uploads router.
    """
    s3, bucket, region = get_s3()
    
    # Sanitize filename
    import re
    safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    
    # S3 key for reports
    s3_key = f"reports/{datetime.utcnow().strftime('%Y/%m/%d')}/{safe_filename}"
    
    try:
        # Upload to S3
        s3.upload_fileobj(
            BytesIO(file_bytes),
            bucket,
            s3_key,
            ExtraArgs={"ContentType": "application/pdf"},
        )
        
        # Generate presigned URL (expires in 7 days)
        download_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=REPORT_PRESIGNED_URL_EXPIRY_SECONDS,
        )
        
        return UploadResult(s3_key=s3_key, download_url=download_url)
    except Exception as e:
        raise RuntimeError(f"S3 upload error: {e}")


# ============================================================
# Helper — Enrich contractor with roles (centralized)
# ============================================================
from core.contractor_helpers import enrich_contractor_with_roles


# ============================================================
# Helper — Generate simple PDF from data
# ============================================================
def generate_pdf_bytes(report_data: Dict[str, Any]) -> bytes:
    """
    Generate a simple PDF from report data.
    Uses reportlab for PDF generation (lightweight approach).
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        # Fallback to simple text if reportlab not available
        return generate_simple_text_pdf(report_data)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=12,
        alignment=TA_CENTER,
    )
    
    # Determine report type
    if "building" in report_data:
        title_text = f"Building Report: {report_data['building'].get('name', 'Unknown')}"
    elif "unit" in report_data:
        unit = report_data["unit"]
        title_text = f"Unit Report: {unit.get('unit_number', 'Unknown')}"
    elif "contractor" in report_data:
        contractor = report_data["contractor"]
        title_text = f"Contractor Report: {contractor.get('company_name', 'Unknown')}"
    else:
        title_text = "Custom Report"
    
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 0.2 * inch))
    
    # Statistics
    stats = report_data.get("statistics", {})
    if stats:
        stats_data = [
            ["Metric", "Value"],
        ]
        for key, value in stats.items():
            stats_data.append([key.replace("_", " ").title(), str(value)])
        
        stats_table = Table(stats_data)
        stats_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 0.3 * inch))
    
    # Events
    events = report_data.get("events", [])
    if events:
        story.append(Paragraph("Events", styles["Heading2"]))
        story.append(Spacer(1, 0.1 * inch))
        
        for event in events[:50]:  # Limit to 50 events
            event_text = f"<b>{event.get('title', 'Untitled')}</b><br/>"
            event_text += f"Type: {event.get('event_type', 'N/A')} | "
            event_text += f"Severity: {event.get('severity', 'N/A')} | "
            event_text += f"Date: {event.get('occurred_at', 'N/A')}"
            if event.get("contractor_notes"):
                event_text += f"<br/>Notes: {event['contractor_notes'][:100]}..."
            story.append(Paragraph(event_text, styles["Normal"]))
            story.append(Spacer(1, 0.05 * inch))
    
    # Documents
    documents = report_data.get("documents", [])
    if documents:
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("Documents", styles["Heading2"]))
        story.append(Spacer(1, 0.1 * inch))
        
        for doc in documents[:50]:  # Limit to 50 documents
            doc_text = f"<b>{doc.get('title', 'Untitled')}</b><br/>"
            doc_text += f"Category: {doc.get('category', 'N/A')} | "
            doc_text += f"Date: {doc.get('created_at', 'N/A')}"
            story.append(Paragraph(doc_text, styles["Normal"]))
            story.append(Spacer(1, 0.05 * inch))
    
    # Footer
    story.append(Spacer(1, 0.3 * inch))
    footer_text = f"Generated: {report_data.get('generated_at', datetime.utcnow().isoformat())}"
    story.append(Paragraph(footer_text, styles["Normal"]))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def generate_simple_text_pdf(report_data: Dict[str, Any]) -> bytes:
    """Fallback: Generate a simple text-based PDF representation."""
    text = f"Report\n{'='*50}\n\n"
    
    if "building" in report_data:
        text += f"Building: {report_data['building'].get('name', 'Unknown')}\n"
    elif "unit" in report_data:
        text += f"Unit: {report_data['unit'].get('unit_number', 'Unknown')}\n"
    elif "contractor" in report_data:
        text += f"Contractor: {report_data['contractor'].get('company_name', 'Unknown')}\n"
    
    text += f"\nGenerated: {report_data.get('generated_at', datetime.utcnow().isoformat())}\n"
    
    return text.encode('utf-8')


# ============================================================
# Main Report Generation Functions
# ============================================================
async def generate_building_report(
    building_id: str,
    user: Optional[CurrentUser],
    context_role: str,
    internal: bool,
    format: str = "json"
) -> ReportResult:
    """
    Generate a building report.
    
    Args:
        building_id: Building ID
        user: Current user (None for public)
        context_role: Effective role (admin, aoao, property_manager, owner, contractor, public)
        internal: Whether this is an internal report (affects visibility)
        format: "json" or "pdf"
    """
    client = get_supabase_client()
    
    # Get building info
    building_result = (
        client.table("buildings")
        .select("*")
        .eq("id", building_id)
        .limit(1)
        .execute()
    )
    
    if not building_result.data:
        raise ValueError(f"Building {building_id} not found")
    
    building = building_result.data[0]
    
    # Get units for this building
    units_result = (
        client.table("units")
        .select("*")
        .eq("building_id", building_id)
        .order("unit_number")
        .execute()
    )
    units = units_result.data or []
    
    # Apply unit filtering for non-admin users
    if user and not is_admin(user) and internal:
        accessible_unit_ids = get_user_accessible_unit_ids(user)
        if accessible_unit_ids is not None:
            units = [u for u in units if u["id"] in accessible_unit_ids]
    
    # Get events for this building
    events_query = client.table("events").select("*").eq("building_id", building_id)
    
    # Apply date filtering if needed (for custom reports)
    # This will be handled by the custom report function
    
    events_result = events_query.order("occurred_at", desc=True).execute()
    events_raw = events_result.data or []
    events = events_raw.copy()
    
    # Filter events by unit access if needed
    if user and not is_admin(user) and internal:
        accessible_unit_ids = get_user_accessible_unit_ids(user)
        if accessible_unit_ids is not None:
            # Get events linked to accessible units
            event_units_result = (
                client.table("event_units")
                .select("event_id")
                .in_("unit_id", accessible_unit_ids)
                .execute()
            )
            accessible_event_ids = {row["event_id"] for row in (event_units_result.data or [])}
            events = [e for e in events if e["id"] in accessible_event_ids]
    
    events_for_counts = events.copy()
    
    # Sanitize events based on role
    sanitized_events = []
    for event in events:
        sanitized = sanitize_event_for_role(event, context_role)
        if sanitized:
            sanitized_events.append(sanitized)
    events = sanitized_events
    
    # Get documents for this building
    documents_query = client.table("documents").select("*").eq("building_id", building_id)
    
    if not internal or context_role == "public":
        # Public reports: Only public documents
        documents_query = documents_query.eq("is_public", True)
    
    documents_result = documents_query.order("created_at", desc=True).execute()
    documents = documents_result.data or []
    
    # Filter documents by unit access if needed
    if user and not is_admin(user) and internal:
        accessible_unit_ids = get_user_accessible_unit_ids(user)
        accessible_building_ids = get_user_accessible_building_ids(user)
        
        # Batch fetch all document_units for all documents (prevents N+1 queries)
        document_ids = [d.get("id") for d in documents if d.get("id")]
        document_units_map = {}
        if document_ids:
            document_units_result = (
                client.table("document_units")
                .select("document_id, unit_id")
                .in_("document_id", document_ids)
                .execute()
            )
            if document_units_result.data:
                for row in document_units_result.data:
                    doc_id = row.get("document_id")
                    unit_id = row.get("unit_id")
                    if doc_id and unit_id:
                        if doc_id not in document_units_map:
                            document_units_map[doc_id] = []
                        document_units_map[doc_id].append(unit_id)
        
        filtered_documents = []
        for document in documents:
            doc_id = document.get("id")
            doc_building_id = document.get("building_id")
            
            if context_role in ["aoao", "aoao_staff"]:
                if accessible_building_ids is None or doc_building_id in accessible_building_ids:
                    filtered_documents.append(document)
                continue
            
            # Check unit access using pre-fetched map
            doc_unit_ids = document_units_map.get(doc_id, [])
            
            if not doc_unit_ids:
                if accessible_building_ids is None or doc_building_id in accessible_building_ids:
                    filtered_documents.append(document)
            else:
                if accessible_unit_ids is None or any(uid in accessible_unit_ids for uid in doc_unit_ids):
                    filtered_documents.append(document)
        
        documents = filtered_documents
    
    # Sanitize documents based on role
    sanitized_documents = []
    for document in documents:
        sanitized = sanitize_document_for_role(document, context_role)
        if sanitized:
            sanitized_documents.append(sanitized)
    documents = sanitized_documents
    
    # Get contractors (via events)
    event_contractors_result = (
        client.table("event_contractors")
        .select("contractor_id, events!inner(building_id)")
        .eq("events.building_id", building_id)
        .execute()
    )
    contractor_ids = list(set([row["contractor_id"] for row in (event_contractors_result.data or []) if row.get("contractor_id")]))
    
    # Count events per contractor
    contractor_event_counts = {}
    for row in (event_contractors_result.data or []):
        cid = row.get("contractor_id")
        if cid:
            contractor_event_counts[cid] = contractor_event_counts.get(cid, 0) + 1
    
    contractors = []
    if contractor_ids:
        contractors_result = (
            client.table("contractors")
            .select("*")
            .in_("id", contractor_ids)
            .execute()
        )
        contractors = contractors_result.data or []
        
        # Batch enrich contractors with roles (prevents N+1 queries)
        from core.contractor_helpers import batch_enrich_contractors_with_roles
        contractors = batch_enrich_contractors_with_roles(contractors)
        
        for contractor in contractors:
            cid = contractor.get("id")
            contractor["event_count"] = contractor_event_counts.get(cid, 0)
    
    # Get property management companies assigned to this building
    pm_building_access_result = (
        client.table("pm_company_building_access")
        .select("pm_company_id")
        .eq("building_id", building_id)
        .execute()
    )
    pm_company_ids_from_building = [row["pm_company_id"] for row in (pm_building_access_result.data or [])]
    
    # Get property management companies assigned to units within this building
    unit_ids = [u["id"] for u in units]
    pm_company_ids_from_units = []
    if unit_ids:
        pm_unit_access_result = (
            client.table("pm_company_unit_access")
            .select("pm_company_id")
            .in_("unit_id", unit_ids)
            .execute()
        )
        pm_company_ids_from_units = [row["pm_company_id"] for row in (pm_unit_access_result.data or [])]
    
    # Combine and deduplicate PM company IDs
    pm_company_ids = list(set(pm_company_ids_from_building + pm_company_ids_from_units))
    
    pm_companies = []
    if pm_company_ids:
        pm_companies_result = (
            client.table("property_management_companies")
            .select("*")
            .in_("id", pm_company_ids)
            .execute()
        )
        pm_companies = pm_companies_result.data or []
    
    # Build quick lookup for event creators to PM/AOAO org names (for event counts)
    def _norm_name(val: Optional[str]) -> Optional[str]:
        return val.strip().lower() if isinstance(val, str) else None
    
    created_by_ids = {e.get("created_by") for e in (events_for_counts or []) if e.get("created_by")}
    user_to_pm_name = {}
    user_to_aoao_name = {}
    for uid in created_by_ids:
        try:
            user_resp = client.auth.admin.get_user_by_id(uid)
            if user_resp and user_resp.user:
                metadata = user_resp.user.user_metadata or {}
                role = (metadata.get("role") or "").lower()
                org_name = metadata.get("organization_name")
                if org_name:
                    norm_org = _norm_name(org_name)
                    if role == "property_manager":
                        user_to_pm_name[uid] = norm_org
                    if role in ["hoa", "hoa_staff"]:
                        user_to_aoao_name[uid] = norm_org
        except Exception:
            continue
    
    # Get AOAO organizations assigned to this building
    aoao_orgs = []
    aoao_building_access_result = (
        client.table("aoao_organization_building_access")
        .select("aoao_organization_id")
        .eq("building_id", building_id)
        .execute()
    )
    aoao_org_ids = [row["aoao_organization_id"] for row in (aoao_building_access_result.data or [])]
    if aoao_org_ids:
        aoao_orgs_result = (
            client.table("aoao_organizations")
            .select("*")
            .in_("id", aoao_org_ids)
            .execute()
        )
        aoao_orgs = aoao_orgs_result.data or []
    
    # Count events per AOAO organization by matching organization_name
    aoao_name_to_id = {}
    for org in aoao_orgs:
        name = _norm_name(org.get("name") or org.get("organization_name"))
        if name:
            aoao_name_to_id[name] = org.get("id")
    
    aoao_event_counts = {}
    for event in (events_for_counts or []):
        uid = event.get("created_by")
        aoao_name = user_to_aoao_name.get(uid)
        if aoao_name and aoao_name in aoao_name_to_id:
            aoao_id = aoao_name_to_id[aoao_name]
            aoao_event_counts[aoao_id] = aoao_event_counts.get(aoao_id, 0) + 1
    
    for org in aoao_orgs:
        org["event_count"] = aoao_event_counts.get(org.get("id"), 0)
    
    # Count events per PM company by matching organization_name
    pm_name_to_id = {}
    for pm in pm_companies:
        name = _norm_name(pm.get("name") or pm.get("company_name"))
        if name:
            pm_name_to_id[name] = pm.get("id")
    
    pm_event_counts = {}
    for event in (events_for_counts or []):
        uid = event.get("created_by")
        pm_name = user_to_pm_name.get(uid)
        if pm_name and pm_name in pm_name_to_id:
            pm_id = pm_name_to_id[pm_name]
            pm_event_counts[pm_id] = pm_event_counts.get(pm_id, 0) + 1
    
    for pm in pm_companies:
        pm["event_count"] = pm_event_counts.get(pm.get("id"), 0)
    
    # Calculate statistics
    stats = {
        "total_events": len(events),
        "total_documents": len(documents),
        "total_units": len(units),
        "total_contractors": len(contractors),
        "total_aoao_organizations": len(aoao_orgs),
        "total_pm_companies": len(pm_companies),
    }
    
    # Build report data
    report_data = {
        "building": building,
        "units": units,
        "events": events,
        "documents": documents,
        "contractors": contractors,
        "aoao_organizations": aoao_orgs,
        "property_management_companies": pm_companies,
        "statistics": stats,
        "generated_at": datetime.utcnow().isoformat(),
        "is_public": not internal,
    }
    
    # Generate report ID and filename
    report_id = str(uuid4())
    building_slug = building.get("name", "building").lower().replace(" ", "-")
    filename = f"building-report-{building_slug}-{datetime.utcnow().strftime('%Y%m%d')}"
    
    # Generate PDF if requested
    download_url = None
    size_bytes = len(str(report_data).encode('utf-8'))
    
    if format == "pdf":
        try:
            pdf_bytes = generate_pdf_bytes(report_data)
            size_bytes = len(pdf_bytes)
            upload_result = await upload_report_to_s3(pdf_bytes, f"{filename}.pdf")
            download_url = upload_result.download_url
            filename = f"{filename}.pdf"
        except Exception as e:
            # Fallback to JSON if PDF generation fails
            format = "json"
            filename = f"{filename}.json"
    
    if format == "json":
        filename = f"{filename}.json"
    
    expires_at = (datetime.utcnow() + timedelta(days=7 if not internal else 30)).isoformat() + "Z"
    
    return ReportResult(
        report_id=report_id,
        filename=filename,
        download_url=download_url,
        expires_at=expires_at,
        size_bytes=size_bytes,
        data=report_data if format == "json" else None,
    )


async def generate_unit_report(
    unit_id: str,
    user: Optional[CurrentUser],
    context_role: str,
    internal: bool,
    format: str = "json"
) -> ReportResult:
    """
    Generate a unit report.
    
    Args:
        unit_id: Unit ID
        user: Current user (None for public)
        context_role: Effective role
        internal: Whether this is an internal report
        format: "json" or "pdf"
    """
    client = get_supabase_client()
    
    # Get unit info
    unit_result = (
        client.table("units")
        .select("*")
        .eq("id", unit_id)
        .limit(1)
        .execute()
    )
    
    if not unit_result.data:
        raise ValueError(f"Unit {unit_id} not found")
    
    unit = unit_result.data[0]
    building_id = unit.get("building_id")
    
    # Get building info
    building = None
    if building_id:
        building_result = (
            client.table("buildings")
            .select("*")
            .eq("id", building_id)
            .limit(1)
            .execute()
        )
        if building_result.data:
            building = building_result.data[0]
    
    # Get events for this unit (via event_units)
    event_units_result = (
        client.table("event_units")
        .select("event_id")
        .eq("unit_id", unit_id)
        .execute()
    )
    event_ids = [row["event_id"] for row in (event_units_result.data or [])]
    
    events = []
    events_raw = []
    if event_ids:
        events_result = (
            client.table("events")
            .select("*")
            .in_("id", event_ids)
            .order("occurred_at", desc=True)
            .execute()
        )
        events_raw = events_result.data or []
        events = events_raw.copy()
    
    # Sanitize events based on role
    events_for_counts = events.copy()
    sanitized_events = []
    for event in events:
        sanitized = sanitize_event_for_role(event, context_role)
        if sanitized:
            sanitized_events.append(sanitized)
    events = sanitized_events
    
    # Get documents for this unit (via document_units)
    document_units_result = (
        client.table("document_units")
        .select("document_id")
        .eq("unit_id", unit_id)
        .execute()
    )
    document_ids = [row["document_id"] for row in (document_units_result.data or [])]
    
    documents = []
    if document_ids:
        documents_query = client.table("documents").select("*").in_("id", document_ids)
        
        if not internal or context_role == "public":
            documents_query = documents_query.eq("is_public", True)
        
        documents_result = documents_query.order("created_at", desc=True).execute()
        documents = documents_result.data or []
    
    # Sanitize documents based on role
    sanitized_documents = []
    for document in documents:
        sanitized = sanitize_document_for_role(document, context_role)
        if sanitized:
            sanitized_documents.append(sanitized)
    documents = sanitized_documents
    
    # Get contractors (via events for this unit)
    contractors = []
    if event_ids:
        event_contractors_result = (
            client.table("event_contractors")
            .select("contractor_id")
            .in_("event_id", event_ids)
            .execute()
        )
        contractor_ids = list(set([row["contractor_id"] for row in (event_contractors_result.data or []) if row.get("contractor_id")]))
        
        # Count events per contractor
        contractor_event_counts = {}
        for row in (event_contractors_result.data or []):
            cid = row.get("contractor_id")
            if cid:
                contractor_event_counts[cid] = contractor_event_counts.get(cid, 0) + 1
        
        if contractor_ids:
            contractors_result = (
                client.table("contractors")
                .select("*")
                .in_("id", contractor_ids)
                .execute()
            )
            contractors = contractors_result.data or []
            
            # Enrich contractors with roles
            for i, contractor in enumerate(contractors):
                contractors[i] = enrich_contractor_with_roles(contractor)
                cid = contractors[i].get("id")
                contractors[i]["event_count"] = contractor_event_counts.get(cid, 0)
    
    # Get property management companies assigned to this unit
    pm_companies = []
    pm_unit_access_result = (
        client.table("pm_company_unit_access")
        .select("pm_company_id")
        .eq("unit_id", unit_id)
        .execute()
    )
    pm_company_ids = [row["pm_company_id"] for row in (pm_unit_access_result.data or [])]
    if pm_company_ids:
        pm_companies_result = (
            client.table("property_management_companies")
            .select("*")
            .in_("id", pm_company_ids)
            .execute()
        )
        pm_companies = pm_companies_result.data or []
    
    # Build quick lookup for event creators to PM/AOAO org names (for event counts)
    def _norm_name(val: Optional[str]) -> Optional[str]:
        return val.strip().lower() if isinstance(val, str) else None
    
    created_by_ids = {e.get("created_by") for e in (events_for_counts or []) if e.get("created_by")}
    user_to_pm_name = {}
    user_to_aoao_name = {}
    for uid in created_by_ids:
        try:
            user_resp = client.auth.admin.get_user_by_id(uid)
            if user_resp and user_resp.user:
                metadata = user_resp.user.user_metadata or {}
                role = (metadata.get("role") or "").lower()
                org_name = metadata.get("organization_name")
                if org_name:
                    norm_org = _norm_name(org_name)
                    if role == "property_manager":
                        user_to_pm_name[uid] = norm_org
                    if role in ["hoa", "hoa_staff"]:
                        user_to_aoao_name[uid] = norm_org
        except Exception:
            continue
    
    # Count events per PM company by matching organization_name
    pm_name_to_id = {}
    for pm in pm_companies:
        name = _norm_name(pm.get("name") or pm.get("company_name"))
        if name:
            pm_name_to_id[name] = pm.get("id")
    
    pm_event_counts = {}
    for event in (events_for_counts or []):
        uid = event.get("created_by")
        pm_name = user_to_pm_name.get(uid)
        if pm_name and pm_name in pm_name_to_id:
            pm_id = pm_name_to_id[pm_name]
            pm_event_counts[pm_id] = pm_event_counts.get(pm_id, 0) + 1
    
    for pm in pm_companies:
        pm["event_count"] = pm_event_counts.get(pm.get("id"), 0)
    
    # Get AOAO organizations assigned to this unit's building
    # (AOAO organizations are assigned at the building level, not unit level)
    aoao_orgs = []
    aoao_org_ids = []
    if building_id:
        try:
            aoao_building_access_result = (
                client.table("aoao_organization_building_access")
                .select("aoao_organization_id")
                .eq("building_id", building_id)
                .execute()
            )
            aoao_org_ids = [row["aoao_organization_id"] for row in (aoao_building_access_result.data or [])]
        except Exception:
            # Table might not exist or error accessing it, continue with empty list
            aoao_org_ids = []
    
    if aoao_org_ids:
        aoao_orgs_result = (
            client.table("aoao_organizations")
            .select("*")
            .in_("id", aoao_org_ids)
            .execute()
        )
        aoao_orgs = aoao_orgs_result.data or []
    
    aoao_name_to_id = {}
    for org in aoao_orgs:
        name = _norm_name(org.get("name") or org.get("organization_name"))
        if name:
            aoao_name_to_id[name] = org.get("id")
    
    aoao_event_counts = {}
    for event in (events_for_counts or []):
        uid = event.get("created_by")
        aoao_name = user_to_aoao_name.get(uid)
        if aoao_name and aoao_name in aoao_name_to_id:
            aoao_id = aoao_name_to_id[aoao_name]
            aoao_event_counts[aoao_id] = aoao_event_counts.get(aoao_id, 0) + 1
    
    for org in aoao_orgs:
        org["event_count"] = aoao_event_counts.get(org.get("id"), 0)
    
    # Calculate statistics
    stats = {
        "total_events": len(events),
        "total_documents": len(documents),
        "total_contractors": len(contractors),
        "total_pm_companies": len(pm_companies),
        "total_aoao_organizations": len(aoao_orgs),
    }
    
    # Build report data
    report_data = {
        "unit": unit,
        "building": building,
        "events": events,
        "documents": documents,
        "contractors": contractors,
        "property_management_companies": pm_companies,
        "aoao_organizations": aoao_orgs,
        "statistics": stats,
        "generated_at": datetime.utcnow().isoformat(),
        "is_public": not internal,
    }
    
    # Generate report ID and filename
    report_id = str(uuid4())
    unit_number = unit.get("unit_number", "unit")
    filename = f"unit-report-{unit_number}-{datetime.utcnow().strftime('%Y%m%d')}"
    
    # Generate PDF if requested
    download_url = None
    size_bytes = len(str(report_data).encode('utf-8'))
    
    if format == "pdf":
        try:
            pdf_bytes = generate_pdf_bytes(report_data)
            size_bytes = len(pdf_bytes)
            upload_result = await upload_report_to_s3(pdf_bytes, f"{filename}.pdf")
            download_url = upload_result.download_url
            filename = f"{filename}.pdf"
        except Exception as e:
            # Fallback to JSON if PDF generation fails
            format = "json"
            filename = f"{filename}.json"
    
    if format == "json":
        filename = f"{filename}.json"
    
    expires_at = (datetime.utcnow() + timedelta(days=7 if not internal else 30)).isoformat() + "Z"
    
    return ReportResult(
        report_id=report_id,
        filename=filename,
        download_url=download_url,
        expires_at=expires_at,
        size_bytes=size_bytes,
        data=report_data if format == "json" else None,
    )


async def generate_contractor_report(
    contractor_id: str,
    user: Optional[CurrentUser],
    context_role: str,
    format: str = "json"
) -> ReportResult:
    """
    Generate a contractor activity report.
    
    Args:
        contractor_id: Contractor ID
        user: Current user
        context_role: Effective role
        format: "json" or "pdf"
    """
    client = get_supabase_client()
    
    # Get contractor info
    contractor_result = (
        client.table("contractors")
        .select("*")
        .eq("id", contractor_id)
        .limit(1)
        .execute()
    )
    
    if not contractor_result.data:
        raise ValueError(f"Contractor {contractor_id} not found")
    
    contractor = contractor_result.data[0]
    contractor = enrich_contractor_with_roles(contractor)
    
    # Get events for this contractor (via event_contractors)
    event_contractors_result = (
        client.table("event_contractors")
        .select("event_id")
        .eq("contractor_id", contractor_id)
        .execute()
    )
    event_ids = [row["event_id"] for row in (event_contractors_result.data or [])]
    
    events = []
    if event_ids:
        events_result = (
            client.table("events")
            .select("*")
            .in_("id", event_ids)
            .order("occurred_at", desc=True)
            .execute()
        )
        events = events_result.data or []
    
    # Sanitize events based on role (contractors see only contractor_notes)
    sanitized_events = []
    for event in events:
        sanitized = sanitize_event_for_role(event, context_role)
        if sanitized:
            sanitized_events.append(sanitized)
    events = sanitized_events
    
    # Get documents for this contractor (via document_contractors)
    document_contractors_result = (
        client.table("document_contractors")
        .select("document_id")
        .eq("contractor_id", contractor_id)
        .execute()
    )
    document_ids = [row["document_id"] for row in (document_contractors_result.data or [])]
    
    documents = []
    if document_ids:
        documents_result = (
            client.table("documents")
            .select("*")
            .in_("id", document_ids)
            .order("created_at", desc=True)
            .execute()
        )
        documents = documents_result.data or []
    
    # Sanitize documents based on role
    sanitized_documents = []
    for document in documents:
        sanitized = sanitize_document_for_role(document, context_role)
        if sanitized:
            sanitized_documents.append(sanitized)
    documents = sanitized_documents
    
    # Get units and buildings from events
    units_map = {}
    buildings_map = {}
    
    if event_ids:
        # Get units via event_units
        event_units_result = (
            client.table("event_units")
            .select("event_id, unit_id, units(*)")
            .in_("event_id", event_ids)
            .execute()
        )
        for row in (event_units_result.data or []):
            if row.get("units"):
                units_map[row["unit_id"]] = row["units"]
        
        # Get buildings from events (query separately to avoid relationship issues)
        # First, get unique building IDs from events
        building_ids = set()
        for event in events:
            if event.get("building_id"):
                building_ids.add(event["building_id"])
        
        # Then query buildings separately
        if building_ids:
            buildings_result = (
                client.table("buildings")
                .select("*")
                .in_("id", list(building_ids))
                .execute()
            )
            for building in (buildings_result.data or []):
                if building.get("id"):
                    buildings_map[building["id"]] = building
    
    # Calculate statistics
    stats = {
        "total_events": len(events),
        "total_documents": len(documents),
        "total_units": len(units_map),
        "total_buildings": len(buildings_map),
    }
    
    # Build report data
    report_data = {
        "contractor": contractor,
        "events": events,
        "documents": documents,
        "units": list(units_map.values()),
        "buildings": list(buildings_map.values()),
        "statistics": stats,
        "generated_at": datetime.utcnow().isoformat(),
    }
    
    # Generate report ID and filename
    report_id = str(uuid4())
    company_name = contractor.get("company_name", "contractor").lower().replace(" ", "-")
    filename = f"contractor-report-{company_name}-{datetime.utcnow().strftime('%Y%m%d')}"
    
    # Generate PDF if requested
    download_url = None
    size_bytes = len(str(report_data).encode('utf-8'))
    
    if format == "pdf":
        try:
            pdf_bytes = generate_pdf_bytes(report_data)
            size_bytes = len(pdf_bytes)
            upload_result = await upload_report_to_s3(pdf_bytes, f"{filename}.pdf")
            download_url = upload_result.download_url
            filename = f"{filename}.pdf"
        except Exception as e:
            # Fallback to JSON if PDF generation fails
            format = "json"
            filename = f"{filename}.json"
    
    if format == "json":
        filename = f"{filename}.json"
    
    expires_at = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
    
    return ReportResult(
        report_id=report_id,
        filename=filename,
        download_url=download_url,
        expires_at=expires_at,
        size_bytes=size_bytes,
        data=report_data if format == "json" else None,
    )


async def generate_custom_report(
    filters: CustomReportFilters,
    user: Optional[CurrentUser],
    context_role: str,
    format: str = "json"
) -> ReportResult:
    """
    Generate a custom report based on filters.
    
    Args:
        filters: CustomReportFilters object
        user: Current user
        context_role: Effective role
        format: "json" or "pdf"
    """
    client = get_supabase_client()
    
    report_data = {
        "events": [],
        "documents": [],
        "units": [],
        "contractors": [],
        "buildings": [],
        "statistics": {},
        "generated_at": datetime.utcnow().isoformat(),
    }
    
    # Get events
    if filters.include_events:
        events_query = client.table("events").select("*")
        
        if filters.building_id:
            events_query = events_query.eq("building_id", filters.building_id)
        
        if filters.unit_ids:
            # Get events via event_units
            event_units_result = (
                client.table("event_units")
                .select("event_id")
                .in_("unit_id", filters.unit_ids)
                .execute()
            )
            event_ids = [row["event_id"] for row in (event_units_result.data or [])]
            if event_ids:
                events_query = events_query.in_("id", event_ids)
            else:
                events_query = events_query.eq("id", "00000000-0000-0000-0000-000000000000")  # No matches
        
        if filters.contractor_ids:
            # Get events via event_contractors
            event_contractors_result = (
                client.table("event_contractors")
                .select("event_id")
                .in_("contractor_id", filters.contractor_ids)
                .execute()
            )
            contractor_event_ids = [row["event_id"] for row in (event_contractors_result.data or [])]
            if contractor_event_ids:
                if filters.unit_ids:
                    # Intersect with unit events
                    event_ids = [eid for eid in event_ids if eid in contractor_event_ids]
                    events_query = events_query.in_("id", event_ids)
                else:
                    events_query = events_query.in_("id", contractor_event_ids)
            else:
                events_query = events_query.eq("id", "00000000-0000-0000-0000-000000000000")  # No matches
        
        if filters.start_date:
            events_query = events_query.gte("occurred_at", filters.start_date.isoformat())
        
        if filters.end_date:
            events_query = events_query.lte("occurred_at", filters.end_date.isoformat())
        
        events_result = events_query.order("occurred_at", desc=True).execute()
        events = events_result.data or []
        
        # Sanitize events
        sanitized_events = []
        for event in events:
            sanitized = sanitize_event_for_role(event, context_role)
            if sanitized:
                sanitized_events.append(sanitized)
        report_data["events"] = sanitized_events
    
    # Get documents
    if filters.include_documents:
        documents_query = client.table("documents").select("*")
        
        if filters.building_id:
            documents_query = documents_query.eq("building_id", filters.building_id)
        
        if filters.unit_ids:
            # Get documents via document_units
            document_units_result = (
                client.table("document_units")
                .select("document_id")
                .in_("unit_id", filters.unit_ids)
                .execute()
            )
            document_ids = [row["document_id"] for row in (document_units_result.data or [])]
            if document_ids:
                documents_query = documents_query.in_("id", document_ids)
            else:
                documents_query = documents_query.eq("id", "00000000-0000-0000-0000-000000000000")  # No matches
        
        if filters.contractor_ids:
            # Get documents via document_contractors
            document_contractors_result = (
                client.table("document_contractors")
                .select("document_id")
                .in_("contractor_id", filters.contractor_ids)
                .execute()
            )
            contractor_document_ids = [row["document_id"] for row in (document_contractors_result.data or [])]
            if contractor_document_ids:
                if filters.unit_ids:
                    # Intersect with unit documents
                    document_ids = [did for did in document_ids if did in contractor_document_ids]
                    documents_query = documents_query.in_("id", document_ids)
                else:
                    documents_query = documents_query.in_("id", contractor_document_ids)
            else:
                documents_query = documents_query.eq("id", "00000000-0000-0000-0000-000000000000")  # No matches
        
        if filters.start_date:
            documents_query = documents_query.gte("created_at", filters.start_date.isoformat())
        
        if filters.end_date:
            documents_query = documents_query.lte("created_at", filters.end_date.isoformat())
        
        documents_result = documents_query.order("created_at", desc=True).execute()
        documents = documents_result.data or []
        
        # Sanitize documents
        sanitized_documents = []
        for document in documents:
            sanitized = sanitize_document_for_role(document, context_role)
            if sanitized:
                sanitized_documents.append(sanitized)
        report_data["documents"] = sanitized_documents
    
    # Calculate statistics
    report_data["statistics"] = {
        "total_events": len(report_data["events"]),
        "total_documents": len(report_data["documents"]),
    }
    
    # Generate report ID and filename
    report_id = str(uuid4())
    filename = f"custom-report-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    
    # Generate PDF if requested
    download_url = None
    size_bytes = len(str(report_data).encode('utf-8'))
    
    if format == "pdf":
        try:
            pdf_bytes = generate_pdf_bytes(report_data)
            size_bytes = len(pdf_bytes)
            upload_result = await upload_report_to_s3(pdf_bytes, f"{filename}.pdf")
            download_url = upload_result.download_url
            filename = f"{filename}.pdf"
        except Exception as e:
            # Fallback to JSON if PDF generation fails
            format = "json"
            filename = f"{filename}.json"
    
    if format == "json":
        filename = f"{filename}.json"
    
    expires_at = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
    
    return ReportResult(
        report_id=report_id,
        filename=filename,
        download_url=download_url,
        expires_at=expires_at,
        size_bytes=size_bytes,
        data=report_data if format == "json" else None,
    )

