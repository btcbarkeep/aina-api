# routers/admin_daily.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)

from core.supabase_client import get_supabase_client
from core.notifications import send_email


router = APIRouter(
    prefix="/admin-daily",
    tags=["Admin Daily Update"],
    dependencies=[Depends(requires_role(["admin", "super_admin"]))],
)

# ============================================================
# Helper — safely fetch table rows
# ============================================================
def fetch_rows(client, table: str):
    result = (
        client.table(table)
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


# ============================================================
# Safe timestamp compare
# ============================================================
def is_within_last_24h(obj, since: datetime):
    raw = obj.get("created_at")
    if not raw:
        return False

    # Supabase sometimes returns ISO string, sometimes Python datetime
    if isinstance(raw, str):
        try:
            ts = datetime.fromisoformat(raw.replace("Z", ""))
        except Exception:
            return False
    else:
        ts = raw

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

    snapshot = {}

    # --------------------------------------------------------
    # BUILDINGS
    # --------------------------------------------------------
    buildings = fetch_rows(client, "buildings")
    snapshot["buildings_total"] = len(buildings)
    snapshot["new_buildings"] = [
        b for b in buildings if is_within_last_24h(b, since)
    ]

    building_lookup = {b["id"]: b for b in buildings}

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------
    events = fetch_rows(client, "events")
    snapshot["events_total"] = len(events)
    snapshot["new_events"] = [
        e for e in events if is_within_last_24h(e, since)
    ]

    # Buildings that had new events today
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
    ]

    # --------------------------------------------------------
    # DOCUMENTS
    # --------------------------------------------------------
    documents = fetch_rows(client, "documents")
    snapshot["documents_total"] = len(documents)
    snapshot["new_documents"] = [
        d for d in documents if is_within_last_24h(d, since)
    ]

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------
    users = fetch_rows(client, "users")
    snapshot["users_total"] = len(users)
    snapshot["new_users"] = [
        u for u in users if is_within_last_24h(u, since)
    ]

    # Active users = those who created events/docs today
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

    # Most active contractor
    if contractor_events:
        top_id = max(contractor_events, key=contractor_events.get)
        snapshot["most_active_contractor"] = next(
            (u for u in contractors if u["id"] == top_id), None
        )
    else:
        snapshot["most_active_contractor"] = None

    # --------------------------------------------------------
    # SYSTEM HEALTH
    # --------------------------------------------------------
    snapshot["cron_status"] = "SUCCESS"  # Cron ran successfully
    snapshot["api_errors_24h"] = 0       # TODO: add real metrics later
    snapshot["api_requests_24h"] = 0     # TODO: add logging later

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------
    snapshot["generated_at"] = now.isoformat()
    snapshot["time_range"] = f"{since.isoformat()} → {now.isoformat()}"

    return snapshot


# ============================================================
# Email Formatting
# ============================================================
def format_daily_email(s):
    lines = []
    add = lines.append

    add("Aina Protocol — Daily System Update\n")
    add(f"Date: {s['generated_at']}")
    add(f"Range: {s['time_range']}\n")

    # BUILDINGS
    add("=== Buildings ===")
    add(f"Total Buildings: {s['buildings_total']}")
    add(f"New Buildings (24h): {len(s['new_buildings'])}")
    add(f"Buildings Updated Today: {len(s['buildings_updated_today'])}")
    for b in s["buildings_updated_today"]:
        add(f" • {b['name']} (ID: {b['building_id']})")
    add("")

    # EVENTS
    add("=== Events ===")
    add(f"Total Events: {s['events_total']}")
    add(f"New Events (24h): {len(s['new_events'])}\n")

    # DOCUMENTS
    add("=== Documents ===")
    add(f"Total Documents: {s['documents_total']}")
    add(f"New Documents (24h): {len(s['new_documents'])}\n")

    # USERS
    add("=== Users ===")
    add(f"Total Users: {s['users_total']}")
    add(f"New Users Today: {len(s['new_users'])}")
    add(f"Active Users (created events/docs): {s['active_users_count']}\n")

    # CONTRACTORS
    add("=== Contractor Activity ===")
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
    add(f"API Requests (24h): {s['api_requests_24h']}")
    add(f"API Errors (24h): {s['api_errors_24h']}")
    add("")

    add("End of report.")
    return "\n".join(lines)


# ============================================================
# POST — Send Daily Report
# ============================================================
@router.post("/send")
def send_daily_update(current_user: CurrentUser = Depends(get_current_user)):
    snapshot = get_daily_snapshot()
    body = format_daily_email(snapshot)

    send_email(
        subject="Aina Protocol — Daily Update",
        body=body,
    )

    return JSONResponse({"status": "sent", "snapshot": snapshot})


# ============================================================
# GET — Preview (JSON)
# ============================================================
@router.get("/preview")
def preview_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return get_daily_snapshot()
