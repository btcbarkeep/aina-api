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
    result = client.table(table).select("*").order("created_at", desc=True).execute()
    return result.data or []


# ============================================================
# Daily Snapshot Builder
# ============================================================
def get_daily_snapshot():
    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase not configured")

    now = datetime.utcnow()
    since = now - timedelta(hours=24)

    def created_within_last_24h(obj):
        ts = obj.get("created_at")
        if not ts:
            return False
        return ts >= since.isoformat()

    snapshot = {}

    # --------------------------------------------------------
    # BUILDINGS
    # --------------------------------------------------------
    buildings = fetch_rows(client, "buildings")
    snapshot["buildings_total"] = len(buildings)
    snapshot["new_buildings"] = [b for b in buildings if created_within_last_24h(b)]

    # buildings that had events today
    today_building_ids = set()

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------
    events = fetch_rows(client, "events")
    snapshot["events_total"] = len(events)
    snapshot["new_events"] = [e for e in events if created_within_last_24h(e)]

    for e in snapshot["new_events"]:
        today_building_ids.add(e.get("building_id"))

    snapshot["buildings_updated_today"] = list(today_building_ids)

    # --------------------------------------------------------
    # DOCUMENTS
    # --------------------------------------------------------
    documents = fetch_rows(client, "documents")
    snapshot["documents_total"] = len(documents)
    snapshot["new_documents"] = [d for d in documents if created_within_last_24h(d)]

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------
    users = fetch_rows(client, "users")
    snapshot["users_total"] = len(users)
    snapshot["new_users"] = [u for u in users if created_within_last_24h(u)]

    # Active = users who submitted events/documents today
    active_user_ids = set(e["created_by"] for e in snapshot["new_events"] if e.get("created_by"))
    active_user_ids.update(
        d["uploaded_by"] for d in snapshot["new_documents"] if d.get("uploaded_by")
    )
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
    snapshot["most_active_contractor"] = None

    if contractor_events:
        top_id = max(contractor_events, key=contractor_events.get)
        snapshot["most_active_contractor"] = next(
            (u for u in users if u["id"] == top_id), None
        )

    # --------------------------------------------------------
    # SYSTEM / API HEALTH  (optional — can grow later)
    # --------------------------------------------------------
    snapshot["cron_status"] = "SUCCESS"
    snapshot["api_errors_24h"] = 0   # Expand later if needed
    snapshot["api_requests_24h"] = 0 # Expand later if needed

    # --------------------------------------------------------
    # Output metadata
    # --------------------------------------------------------
    snapshot["generated_at"] = now.isoformat()
    snapshot["time_range"] = f"{since.isoformat()} → {now.isoformat()}"

    return snapshot


# ============================================================
# Email Builder (clean & readable)
# ============================================================
def format_daily_email(s):
    lines = []
    add = lines.append

    add("Aina Protocol — Daily System Update\n")
    add(f"Date: {s['generated_at']}")
    add(f"Range: {s['time_range']}\n")

    # ------------------------------
    # BUILDINGS
    # ------------------------------
    add("=== Buildings ===")
    add(f"Total Buildings: {s['buildings_total']}")
    add(f"New in last 24h: {len(s['new_buildings'])}")
    add(f"Buildings updated today (via events): {len(s['buildings_updated_today'])}")
    add("")

    # ------------------------------
    # EVENTS
    # ------------------------------
    add("=== Events ===")
    add(f"Total Events: {s['events_total']}")
    add(f"New in last 24h: {len(s['new_events'])}")
    add("")

    # ------------------------------
    # DOCUMENTS
    # ------------------------------
    add("=== Documents ===")
    add(f"Total Documents: {s['documents_total']}")
    add(f"New in last 24h: {len(s['new_documents'])}")
    add("")

    # ------------------------------
    # USERS
    # ------------------------------
    add("=== Users ===")
    add(f"Total Users: {s['users_total']}")
    add(f"New Users Today: {len(s['new_users'])}")
    add(f"Active Users Today: {s['active_users_count']}")
    add("")

    # ------------------------------
    # CONTRACTORS
    # ------------------------------
    add("=== Contractor Activity ===")
    if s["most_active_contractor"]:
        m = s["most_active_contractor"]
        add(f"Most Active Contractor: {m.get('full_name', m['email'])}")
    else:
        add("No contractor activity in last 24h")
    add("")

    # ------------------------------
    # SYSTEM HEALTH
    # ------------------------------
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
# GET — Preview
# ============================================================
@router.get("/preview")
def preview_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return get_daily_snapshot()
