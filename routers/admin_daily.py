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


router = APIRouter(
    prefix="/admin-daily",
    tags=["Admin Daily"],
    dependencies=[Depends(requires_permission("admin:daily_send"))],
)


# ============================================================
# Supabase Auth Users (replaces old users table)
# ============================================================
def fetch_auth_users():
    client = get_supabase_client()
    try:
        raw = client.auth.admin.list_users()
        return raw.get("users", raw) if isinstance(raw, dict) else raw
    except Exception as e:
        raise HTTPException(500, f"Supabase user fetch failed: {e}")


# ============================================================
# Basic DB fetch helper
# ============================================================
def fetch_rows(table: str):
    rows = safe_select(table)
    return rows or []


# ============================================================
# Timestamp parsing
# ============================================================
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
    ts = parse_timestamp(obj.get("created_at"))
    return ts and ts >= since


# ============================================================
# Build the daily snapshot (NO EMAIL)
# ============================================================
def build_snapshot():
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    snapshot = {
        "generated_at": now.isoformat(),
        "range": f"{since.isoformat()} → {now.isoformat()}",
    }

    # BUILDINGS
    buildings = fetch_rows("buildings")
    snapshot["buildings_total"] = len(buildings)
    snapshot["new_buildings"] = [b for b in buildings if is_within_last_24h(b, since)]

    building_lookup = {b["id"]: b for b in buildings}

    # EVENTS
    events = fetch_rows("events")
    snapshot["events_total"] = len(events)
    snapshot["new_events"] = [e for e in events if is_within_last_24h(e, since)]

    snapshot["buildings_updated"] = [
        {
            "building_id": eid.get("building_id"),
            "name": building_lookup.get(eid.get("building_id"), {}).get("name", "Unknown")
        }
        for eid in snapshot["new_events"]
        if eid.get("building_id")
    ]

    # DOCUMENTS
    documents = fetch_rows("documents")
    snapshot["documents_total"] = len(documents)
    snapshot["new_documents"] = [d for d in documents if is_within_last_24h(d, since)]

    # USERS
    users = fetch_auth_users()
    snapshot["users_total"] = len(users)
    snapshot["new_users"] = [
        u for u in users if is_within_last_24h(u, since)
    ]

    # Active users
    active_user_ids = set()
    for e in snapshot["new_events"]:
        if e.get("created_by"):
            active_user_ids.add(e["created_by"])

    for d in snapshot["new_documents"]:
        if d.get("uploaded_by"):
            active_user_ids.add(d["uploaded_by"])

    snapshot["active_users"] = len(active_user_ids)

    # CONTRACTORS
    contractors = [
        u for u in users
        if (u.get("user_metadata") or {}).get("role") == "contractor"
    ]

    contractor_activity = {}
    for e in snapshot["new_events"]:
        uid = e.get("created_by")
        if uid:
            contractor_activity[uid] = contractor_activity.get(uid, 0) + 1

    snapshot["contractor_activity"] = contractor_activity

    if contractor_activity:
        top_id = max(contractor_activity, key=contractor_activity.get)
        snapshot["top_contractor"] = next(
            (u for u in contractors if u.get("id") == top_id),
            None,
        )
    else:
        snapshot["top_contractor"] = None

    return snapshot


# ============================================================
# 1️⃣ Manual — run snapshot (dashboard button)
# ============================================================
@router.post("/run")
def run_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    snapshot = build_snapshot()
    return JSONResponse({"success": True, "snapshot": snapshot})


# ============================================================
# 2️⃣ Manual — preview endpoint (also protected)
# ============================================================
@router.get("/preview")
def preview_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return {"success": True, "data": build_snapshot()}
