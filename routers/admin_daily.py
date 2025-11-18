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
# Normalize Supabase Auth User object → dict
# ============================================================
def normalize_auth_user(u):
    return {
        "id": getattr(u, "id", None),
        "email": getattr(u, "email", None),
        "created_at": getattr(u, "created_at", None),
        "role": (u.user_metadata or {}).get("role"),
        "user_metadata": u.user_metadata or {},
    }


# ============================================================
# Fetch Auth Users
# ============================================================
def fetch_auth_users():
    client = get_supabase_client()

    try:
        result = client.auth.admin.list_users()

        # Supabase SDK returns:
        #   { "users": [UserObject, ...] }
        users_raw = result.get("users", [])

        # Convert all Supabase User objects → dicts
        return [normalize_auth_user(u) for u in users_raw]

    except Exception as e:
        raise HTTPException(500, f"Supabase user fetch failed: {e}")


# ============================================================
# Basic DB fetch
# ============================================================
def fetch_rows(table: str):
    return safe_select(table) or []


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


# ============================================================
# 24-hour check
# ============================================================
def is_within_last_24h(obj: dict, since: datetime):
    ts = parse_timestamp(obj.get("created_at"))
    return ts and ts >= since


# ============================================================
# Build snapshot
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

    # EVENTS
    events = fetch_rows("events")
    snapshot["events_total"] = len(events)
    snapshot["new_events"] = [e for e in events if is_within_last_24h(e, since)]

    # Documents
    documents = fetch_rows("documents")
    snapshot["documents_total"] = len(documents)
    snapshot["new_documents"] = [d for d in documents if is_within_last_24h(d, since)]

    # USERS (Auth)
    users = fetch_auth_users()
    snapshot["users_total"] = len(users)
    snapshot["new_users"] = [
        u for u in users if is_within_last_24h(u, since)
    ]

    # Active users (events + documents)
    active_user_ids = set()

    for e in snapshot["new_events"]:
        if e.get("created_by"):
            active_user_ids.add(e["created_by"])

    for d in snapshot["new_documents"]:
        if d.get("uploaded_by"):
            active_user_ids.add(d["uploaded_by"])

    snapshot["active_users"] = len(active_user_ids)

    # Contractor users
    contractors = [u for u in users if u.get("role") == "contractor"]

    contractor_activity = {}
    for e in snapshot["new_events"]:
        uid = e.get("created_by")
        if uid:
            contractor_activity[uid] = contractor_activity.get(uid, 0) + 1

    snapshot["contractor_activity"] = contractor_activity

    if contractor_activity:
        top_id = max(contractor_activity, key=contractor_activity.get)
        snapshot["top_contractor"] = next(
            (u for u in contractors if u["id"] == top_id),
            None
        )
    else:
        snapshot["top_contractor"] = None

    return snapshot


# ============================================================
# ROUTES
# ============================================================
@router.post("/run")
def run_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return {"success": True, "snapshot": build_snapshot()}


@router.get("/preview")
def preview_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return {"success": True, "data": build_snapshot()}
