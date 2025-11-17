# routers/admin_daily.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta

from dependencies.auth import (
    get_current_user,
    CurrentUser,
)

# NEW permission system
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
# Helper — safely fetch full table rows
# ============================================================
def fetch_rows(table: str):
    """Returns all rows from a table using safe_select."""
    rows = safe_select(table)
    return rows or []


# ============================================================
# Timestamp parsing helper
# ============================================================
def parse_timestamp(value):
    """Parse Supabase timestamps safely."""
    if not value:
        return None

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", ""))
        except Exception:
            return None

    if isinstance(value, datetime):
        return value

    return None


# ============================================================
# Check if object is created in the last 24 hours
# ============================================================
def is_within_last_24h(obj, since: datetime):
    ts = parse_timestamp(obj.get("created_at"))
    if not ts:
        return False
    return ts >= since


# ============================================================
# Daily Snapshot Builder
# ============================================================
def get_daily_snapshot():
    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase not configured")

    now = datetime.utcnow()
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
    snapshot["new_buildings"] = [
        b for b in buildings if is_within_last_24h(b, since)
    ]

    building_lookup = {b["id"]: b for b in buildings}

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------
    events = fetch_rows("events")
    snapshot["events_total"] = len(events)
    snapshot["new_events"] = [
        e for e in events if is_within_last_24h(e, since)
    ]

    updated_b_ids = {
        e.get("building_id")
        for e in snapshot["new_events"]
        if e.get("building_id")
    }

    snapshot["buildings_updated_today"] = [
        {
            "building_id": bid,
            "name": building_lookup.get(bid, {}).get("name", "Unknown"),
        }
        for bid in updated_b_ids
        if bid is not None
    ]

    # --------------------------------------------------------
    # DOCUMENTS
    # --------------------------------------------------------
    documents = fetch_rows("documents")
    snapshot["documents_total"] = len(documents)
    snapshot["new_documents"] = [
        d for d in documents if is_within_last_24h(d, since)
    ]

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------
    users = fetch_rows("users")
    snapshot["users_total"] = len(users)
    snapshot["new_users"] = [
        u for u in users if is_within_last_24h(u, since)
    ]

    # Active users = created an event or uploaded a doc
    active_user_ids = set()

    for e in snapshot["new_events"]:
        if e.get("created_by"):
            active_user_ids.add(e["created_by"])

    for d in snapshot["new_documents"]:
        if d.get("uploaded_by"):
            active_user_ids.add(d["uploaded_by"])

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
            None
        )
    else:
        snapshot["most_active_contractor"] = None

    # --------------------------------------------------------
    # SYSTEM HEALTH (placeholders for now)
    # --------------------------------------------------------
    snapshot["cron_status"] = "SUCCESS"
    snapshot["api_errors_24h"] = 0
    snapshot["api_requests_24h"] = 0

    return snapshot


# ============================================================
# Format email content
# ============================================================
def format_daily_email(s):
    lines = []
    add = lines.append

    add("Aina Protocol — Daily System Update\n")
    add(f"Generated: {s['generated_at']}")
    add(f"Range: {s['time_range']}\n")

    # BUILDINGS
    add("=== Buildings ===")
    add(f"Total Buildings: {s['buildings_total']}")
    add(f"New Buildings: {len(s['new_buildings'])}")
    add(f"Buildings Updated Today: {len(s['buildings_updated_today'])}")
    for b in s["buildings_updated_today"]:
        add(f" • {b['name']} (ID: {b['building_id']})")
    add("")

    # EVENTS
    add("=== Events ===")
    add(f"Total Events: {s['events_total']}")
    add(f"New Events: {len(s['new_events'])}\n")

    # DOCUMENTS
    add("=== Documents ===")
    add(f"Total Documents: {s['documents_total']}")
    add(f"New Documents: {len(s['new_documents'])}\n")

    # USERS
    add("=== Users ===")
    add(f"Total Users: {s['users_total']}")
    add(f"New Users: {len(s['new_users'])}")
    add(f"Active Users: {s['active_users_count']}\n")

    # CONTRACTORS
    add("=== Contractors ===")
    if s["most_active_contractor"]:
        m = s["most_active_contractor"]
        add(f"Most Active Contractor: {m.get('full_name') or m['email']}")
        add(f"Events Today: {s['contractor_activity'][m['id']]}")
    else:
        add("No contractor activity in last 24h")
    add("")

    # SYSTEM HEALTH
    add("=== System Health ===")
    add(f"Cron Status: {s['cron_status']}")
    add(f"API Requests: {s['api_requests_24h']}")
    add(f"API Errors: {s['api_errors_24h']}")
    add("")

    add("End of report.")
    return "\n".join(lines)


# ============================================================
# POST — Send Daily Email
# ============================================================
@router.post("/send")
def send_daily_update(current_user: CurrentUser = Depends(get_current_user)):
    snapshot = get_daily_snapshot()
    email_body = format_daily_email(snapshot)

    send_email(
        subject="Aina Protocol — Daily Update",
        body=email_body,
    )

    return JSONResponse({"success": True, "snapshot": snapshot})


# ============================================================
# GET — Preview Snapshot (JSON)
# ============================================================
@router.get("/preview")
def preview_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return {"success": True, "data": get_daily_snapshot()}
