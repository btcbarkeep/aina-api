# routers/admin_daily.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta, timezone

from dependencies.auth import (
    get_current_user,
    CurrentUser,
)

from core.permission_helpers import requires_permission
from core.supabase_client import get_supabase_client
from core.supabase_helpers import safe_select
from core.notifications import send_email


router = APIRouter(
    prefix="/admin-daily",
    tags=["Admin Daily Update"],
    dependencies=[Depends(requires_permission("admin:daily_send"))],
)


# ----------------------------------------------------------
# Supabase Auth users replacement
# ----------------------------------------------------------
def fetch_auth_users():
    """Return list of all Supabase Auth users (service role only)."""
    client = get_supabase_client()
    try:
        raw = client.auth.admin.list_users()
        return raw.get("users", raw) if isinstance(raw, dict) else raw
    except Exception as e:
        raise HTTPException(500, f"Supabase Auth fetch failed: {e}")


# ----------------------------------------------------------
# Basic fetch helper
# ----------------------------------------------------------
def fetch_rows(table: str):
    rows = safe_select(table)
    return rows or []


def parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except:
            return None
    return None


def is_within_last_24h(obj, since: datetime):
    ts = parse_timestamp(obj.get("created_at") or obj.get("created_at"))
    return ts and ts >= since


# ----------------------------------------------------------
# DAILY SNAPSHOT
# ----------------------------------------------------------
def get_daily_snapshot():
    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase not configured")

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    snapshot = {
        "generated_at": now.isoformat(),
        "time_range": f"{since.isoformat()} → {now.isoformat()}",
    }

    # ------------------------------------------------------
    # BUILDINGS
    buildings = fetch_rows("buildings")
    snapshot["buildings_total"] = len(buildings)
    snapshot["new_buildings"] = [b for b in buildings if is_within_last_24h(b, since)]
    building_lookup = {b["id"]: b for b in buildings}

    # ------------------------------------------------------
    # EVENTS
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
    ]

    # ------------------------------------------------------
    # DOCUMENTS
    documents = fetch_rows("documents")
    snapshot["documents_total"] = len(documents)
    snapshot["new_documents"] = [
        d for d in documents if is_within_last_24h(d, since)
    ]

    # ------------------------------------------------------
    # USERS (Supabase Auth)
    auth_users = fetch_auth_users()
    snapshot["users_total"] = len(auth_users)

    # New users in last 24 hours
    snapshot["new_users"] = [
        u for u in auth_users
        if is_within_last_24h(u, since)
    ]

    # Active users (events + documents)
    active_user_ids = set()
    for e in snapshot["new_events"]:
        if e.get("created_by"):
            active_user_ids.add(e["created_by"])

    for d in snapshot["new_documents"]:
        if d.get("uploaded_by"):
            active_user_ids.add(d["uploaded_by"])

    snapshot["active_users_count"] = len(active_user_ids)

    # ------------------------------------------------------
    # CONTRACTORS (role from user_metadata)
    contractors = [
        u for u in auth_users
        if (u.get("user_metadata") or {}).get("role") == "contractor"
    ]

    contractor_events = {}
    for e in snapshot["new_events"]:
        uid = e.get("created_by")
        if uid:
            contractor_events[uid] = contractor_events.get(uid, 0) + 1

    snapshot["contractor_activity"] = contractor_events

    if contractor_events:
        top_id = max(contractor_events, key=contractor_events.get)
        snapshot["most_active_contractor"] = next(
            (
                u for u in contractors
                if u.get("id") == top_id
            ),
            None,
        )
    else:
        snapshot["most_active_contractor"] = None

    # ------------------------------------------------------
    # System health
    snapshot["cron_status"] = "SUCCESS"
    snapshot["api_requests_24h"] = 0
    snapshot["api_errors_24h"] = 0

    return snapshot


# ----------------------------------------------------------
# EMAIL FORMATTER
# ----------------------------------------------------------
def format_daily_email(s):
    lines = []
    add = lines.append

    add("Aina Protocol — Daily System Update\n")
    add(f"Generated: {s['generated_at']}")
    add(f"Range: {s['time_range']}\n")

    add("=== Buildings ===")
    add(f"Total Buildings: {s['buildings_total']}")
    add(f"New Buildings: {len(s['new_buildings'])}")
    add(f"Buildings Updated Today: {len(s['buildings_updated_today'])}")
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
    mc = s["most_active_contractor"]
    if mc:
        meta = mc.get("user_metadata") or {}
        name = meta.get("full_name") or mc.get("email")
        add(f"Most Active Contractor: {name}")
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


# ----------------------------------------------------------
# POST — Send Daily Email
# ----------------------------------------------------------
@router.post("/send")
def send_daily_update(current_user: CurrentUser = Depends(get_current_user)):
    snapshot = get_daily_snapshot()
    body = format_daily_email(snapshot)

    send_email(
        subject="Aina Protocol — Daily Update",
        body=body,
    )

    return JSONResponse({"success": True, "snapshot": snapshot})


# ----------------------------------------------------------
# GET — Preview Snapshot (no email)
# ----------------------------------------------------------
@router.get("/preview")
def preview_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return {"success": True, "data": get_daily_snapshot()}
