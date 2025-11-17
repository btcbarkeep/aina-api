# routers/admin_daily.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta, timezone

from dependencies.auth import (
    get_current_user,
    CurrentUser,
)

# Permission-based global RBAC
from core.permission_helpers import requires_permission

# Supabase helpers
from core.supabase_client import get_supabase_client
from core.supabase_helpers import safe_select
from core.notifications import send_email


router = APIRouter(
    prefix="/admin-daily",
    tags=["Admin Daily Update"],
    dependencies=[Depends(requires_permission("admin:daily_send"))],
)


# ============================================================
# Helper — safely fetch all table rows
# ============================================================
def fetch_rows(table: str):
    """
    Uses safe_select() to return every row for a table.
    Always returns list (never None).
    """
    rows = safe_select(table)
    return rows or []


# ============================================================
# Timestamp parsing helper
# ============================================================
def parse_timestamp(value):
    """
    Accepts Supabase UTC strings or naive datetimes.
    Ensures result is a timezone-aware UTC datetime.
    """

    if not value:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, str):
        try:
            # Supabase ISO8601 fix
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    return None


# ============================================================
# Created within the last 24 hours
# ============================================================
def is_within_last_24h(obj, since: datetime):
    ts = parse_timestamp(obj.get("created_at"))
    if not ts:
        return False
    return ts >= since


# ============================================================
# DAILY SNAPSHOT BUILDER
# ============================================================
def get_daily_snapshot():
    """
    Builds a complete system snapshot of:
    - Buildings
    - Events
    - Documents
    - Users
    - Contractor activity
    - System health (placeholders)

    All using Supabase.
    """
    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase not configured")

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    snapshot = {
        "generated_at": now.isoformat(),
        "time_range": f"{since.isoformat()} → {now.isoformat()}",
    }

    # --------------------------------------------------------
    # BUILDINGS
    # --------------------------------------------------------
    buildings = fetch_rows("buildings")
    snapshot["buildings_total"] = len(buildings)
    snapshot["new_buildings"] = [b for b in buildings if is_within_last_24h(b, since)]

    building_lookup = {b["id"]: b for b in buildings}

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------
    events = fetch_rows("events")
    snapshot["events_total"] = len(events)
    snapshot["new_events"] = [e for e in events if is_within_last_24h(e, since)]

    updated_building_ids = {
        e.get("building_id") for e in snapshot["new_events"] if e.get("building_id")
    }

    snapshot["buildings_updated_today"] = [
        {
            "building_id": bid,
            "name": building_lookup.get(bid, {}).get("name", "Unknown"),
        }
        for bid in updated_building_ids
        if bid is not None
    ]

    # --------------------------------------------------------
    # DOCUMENTS
    # --------------------------------------------------------
    documents = fetch_rows("documents")
    snapshot["documents_total"] = len(documents)
    snapshot["new_documents"] = [d for d in documents if is_within_last_24h(d, since)]

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------
    users = fetch_rows("users")
    snapshot["users_total"] = len(users)
    snapshot["new_users"] = [u for u in users if is_within_last_24h(u, since)]

    active_user_ids = set()

    # Activity from events
    for e in snapshot["new_events"]:
        uid = e.get("created_by")
        if uid:
            active_user_ids.add(uid)

    # Activity from documents
    for d in snapshot["new_documents"]:
        uid = d.get("uploaded_by")
        if uid:
            active_user_ids.add(uid)

    snapshot["active_users_count"] = len(active_user_ids)

    # --------------------------------------------------------
    # CONTRACTOR ACTIVITY
    # --------------------------------------------------------
    contractors = [u for u in users if u.get("role") == "contractor"]

    contractor_events = {}
    for e in snapshot["new_events"]:
        cid = e.get("created_by")
        if cid:
            contractor_events[cid] = contractor_events.get(cid, 0) + 1

    snapshot["contractor_activity"] = contractor_events

    if contractor_events:
        top_id = max(contractor_events, key=contractor_events.get)
        snapshot["most_active_contractor"] = next(
            (u for u in contractors if u["id"] == top_id),
            None,
        )
    else:
        snapshot["most_active_contractor"] = None

    # --------------------------------------------------------
    # SYSTEM HEALTH (placeholder values)
    # --------------------------------------------------------
    snapshot["cron_status"] = "SUCCESS"
    snapshot["api_requests_24h"] = 0
    snapshot["api_errors_24h"] = 0

    return snapshot


# ============================================================
# EMAIL FORMATTER
# ============================================================
def format_daily_email(s):
    """Return a clean plain text email body."""
    lines = []
    add = lines.append

    add("Aina Protocol — Daily System Update\n")
    add(f"Generated: {s['generated_at']}")
    add(f"Range: {s['time_range']}\n")

    add("=== Buildings ===")
    add(f"Total Buildings: {s['buildings_total']}")
    add(f"New Buildings: {len(s['new_buildings'])}")
    add(f"Buildings Updated Today: {len(s['buildings_updated_today'])}")
    for b in s["buildings_updated_today"]:
        add(f" • {b['name']} (ID: {b['building_id']})")
    add("")

    add("=== Events ===")
    add(f"Total Events: {s['events_total']}")
    add(f"New Events: {len(s['new_events'])}\n")

    add("=== Documents ===")
    add(f"Total Documents: {s['documents_total']}")
    add(f"New Documents: {len(s['new_documents'])}\n")

    add("=== Users ===")
    add(f"Total Users: {s['users_total']}")
    add(f"New Users: {len(s['new_users'])}")
    add(f"Active Users: {s['active_users_count']}\n")

    add("=== Contractors ===")
    if s["most_active_contractor"]:
        mc = s["most_active_contractor"]
        add(f"Most Active Contractor: {mc.get('full_name') or mc.get('email')}")
        add(f"Events Today: {s['contractor_activity'][mc['id']]}")
    else:
        add("No contractor activity in last 24h")
    add("")

    add("=== System Health ===")
    add(f"Cron Status: {s['cron_status']}")
    add(f"API Requests (24h): {s['api_requests_24h']}")
    add(f"API Errors (24h): {s['api_errors_24h']}")
    add("")

    add("End of report.")
    return "\n".join(lines)


# ============================================================
# POST — Send Daily Update Email
# ============================================================
@router.post("/send")
def send_daily_update(current_user: CurrentUser = Depends(get_current_user)):
    snapshot = get_daily_snapshot()
    body = format_daily_email(snapshot)

    send_email(
        subject="Aina Protocol — Daily Update",
        body=body,
    )

    return JSONResponse({"success": True, "snapshot": snapshot})


# ============================================================
# GET — Preview Snapshot (no email)
# ============================================================
@router.get("/preview")
def preview_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return {"success": True, "data": get_daily_snapshot()}
