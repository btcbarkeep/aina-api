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
# Fetch Supabase Auth Users — FIXED for Supabase 2.x
# ============================================================
def fetch_auth_users():
    client = get_supabase_client()
    try:
        resp = client.auth.admin.list_users()
        return resp.users  # This is a list[User] Pydantic model
    except Exception as e:
        raise HTTPException(500, f"Supabase user fetch failed: {e}")


# ============================================================
# Fetch any DB table rows (dicts)
# ============================================================
def fetch_rows(table: str):
    rows = safe_select(table)
    return rows or []


# ============================================================
# Timestamp parsing (supports DB strings + Supabase Auth strings)
# ============================================================
def parse_timestamp(value):
    if not value:
        return None

    # Already a datetime
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    # string → datetime
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    return None


# ============================================================
# Check if DB row (dict) created_at is within last 24h
# ============================================================
def is_row_within_last_24h(row: dict, since: datetime):
    ts = parse_timestamp(row.get("created_at"))
    return ts and ts >= since


# ============================================================
# Check if AUTH USER (Pydantic) created_at is within last 24h
# ============================================================
def is_auth_user_within_last_24h(user_obj, since: datetime):
    ts = parse_timestamp(user_obj.created_at)
    return ts and ts >= since


# ============================================================
# Build Daily Snapshot
# ============================================================
def build_snapshot():
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    snapshot = {
        "generated_at": now.isoformat(),
        "range": f"{since.isoformat()} → {now.isoformat()}",
    }

    # --------------------------------------------------------
    # BUILDINGS (dicts)
    # --------------------------------------------------------
    buildings = fetch_rows("buildings")
    snapshot["buildings_total"] = len(buildings)
    snapshot["new_buildings"] = [
        b for b in buildings if is_row_within_last_24h(b, since)
    ]

    building_lookup = {b["id"]: b for b in buildings}

    # --------------------------------------------------------
    # EVENTS (dicts)
    # --------------------------------------------------------
    events = fetch_rows("events")
    snapshot["events_total"] = len(events)
    snapshot["new_events"] = [
        e for e in events if is_row_within_last_24h(e, since)
    ]

    # Which buildings had new events
    snapshot["buildings_updated"] = [
        {
            "building_id": e.get("building_id"),
            "name": building_lookup.get(e.get("building_id"), {}).get("name", "Unknown")
        }
        for e in snapshot["new_events"]
        if e.get("building_id")
    ]

    # --------------------------------------------------------
    # DOCUMENTS (dicts)
    # --------------------------------------------------------
    documents = fetch_rows("documents")
    snapshot["documents_total"] = len(documents)
    snapshot["new_documents"] = [
        d for d in documents if is_row_within_last_24h(d, since)
    ]

    # --------------------------------------------------------
    # SUPABASE AUTH USERS (objects, not dicts)
    # --------------------------------------------------------
    users = fetch_auth_users()
    snapshot["users_total"] = len(users)

    snapshot["new_users"] = [
        {
            "id": u.id,
            "email": u.email,
            "created_at": u.created_at,
        }
        for u in users
        if is_auth_user_within_last_24h(u, since)
    ]

    # --------------------------------------------------------
    # ACTIVE USERS (from events + documents)
    # --------------------------------------------------------
    active_user_ids = set()

    for e in snapshot["new_events"]:
        if e.get("created_by"):
            active_user_ids.add(e["created_by"])

    for d in snapshot["new_documents"]:
        if d.get("uploaded_by"):
            active_user_ids.add(d["uploaded_by"])

    snapshot["active_users"] = len(active_user_ids)

    # --------------------------------------------------------
    # CONTRACTORS — look into user_metadata.role
    # --------------------------------------------------------
    contractors = [
        u for u in users
        if (u.user_metadata or {}).get("role") == "contractor"
    ]

    contractor_activity = {}

    for e in snapshot["new_events"]:
        uid = e.get("created_by")
        if uid:
            contractor_activity[uid] = contractor_activity.get(uid, 0) + 1

    snapshot["contractor_activity"] = contractor_activity

    if contractor_activity:
        top_contractor_id = max(contractor_activity, key=contractor_activity.get)
        snapshot["top_contractor"] = next(
            (
                {
                    "id": u.id,
                    "email": u.email,
                    "events_created": contractor_activity.get(u.id, 0),
                }
                for u in contractors
                if u.id == top_contractor_id
            ),
            None,
        )
    else:
        snapshot["top_contractor"] = None

    return snapshot


# ============================================================
# POST /admin-daily/run — Manual Snapshot
# ============================================================
@router.post("/run")
def run_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    snapshot = build_snapshot()
    return JSONResponse({"success": True, "snapshot": snapshot})


# ============================================================
# GET /admin-daily/preview — Manual Preview
# ============================================================
@router.get("/preview")
def preview_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return {"success": True, "data": build_snapshot()}
