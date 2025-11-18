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
# SAFE: Fetch & normalize Supabase Auth users
# ============================================================
def fetch_auth_users():
    client = get_supabase_client()

    try:
        result = client.auth.admin.list_users()

        # The Supabase client returns an object with "users", OR a raw list
        raw_users = []

        if hasattr(result, "users"):
            raw_users = result.users
        elif isinstance(result, list):
            raw_users = result
        else:
            # Last fallback — convert dict-like or unknown format
            raw_users = result.get("users", [])

        normalized = []

        for u in raw_users:
            # Some clients return dict form; some return class form
            if isinstance(u, dict):
                normalized.append({
                    "id": u.get("id"),
                    "email": u.get("email"),
                    "created_at": u.get("created_at"),
                    "last_sign_in_at": u.get("last_sign_in_at"),
                    "user_metadata": u.get("user_metadata") or {},
                })
            else:
                # AuthUser class instance
                normalized.append({
                    "id": getattr(u, "id", None),
                    "email": getattr(u, "email", None),
                    "created_at": getattr(u, "created_at", None),
                    "last_sign_in_at": getattr(u, "last_sign_in_at", None),
                    "user_metadata": getattr(u, "user_metadata", {}) or {},
                })

        return normalized

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


def is_within_last_24h(obj: dict, since: datetime):
    if not isinstance(obj, dict):
        return False
    ts = parse_timestamp(obj.get("created_at"))
    return ts and ts >= since


# ============================================================
# Build daily snapshot
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

    building_lookup = {b.get("id"): b for b in buildings}

    # EVENTS
    events = fetch_rows("events")
    snapshot["events_total"] = len(events)
    snapshot["new_events"] = [e for e in events if is_within_last_24h(e, since)]

    snapshot["buildings_updated"] = [
        {
            "building_id": e.get("building_id"),
            "name": building_lookup.get(e.get("building_id"), {}).get("name", "Unknown")
        }
        for e in snapshot["new_events"]
        if isinstance(e, dict) and e.get("building_id")
    ]

    # DOCUMENTS
    documents = fetch_rows("documents")
    snapshot["documents_total"] = len(documents)
    snapshot["new_documents"] = [d for d in documents if is_within_last_24h(d, since)]

    # USERS (Supabase Auth)
    users = fetch_auth_users()
    snapshot["users_total"] = len(users)
    snapshot["new_users"] = [u for u in users if is_within_last_24h(u, since)]

    # ACTIVE USERS
    active_user_ids = set()

    for e in snapshot["new_events"]:
        if isinstance(e, dict) and e.get("created_by"):
            active_user_ids.add(e["created_by"])

    for d in snapshot["new_documents"]:
        if isinstance(d, dict) and d.get("uploaded_by"):
            active_user_ids.add(d["uploaded_by"])

    snapshot["active_users"] = len(active_user_ids)

    # CONTRACTORS
    contractors = [
        u for u in users
        if (u.get("user_metadata") or {}).get("role") == "contractor"
    ]

    contractor_activity = {}
    for e in snapshot["new_events"]:
        if isinstance(e, dict):
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
# Endpoints
# ============================================================
@router.post("/run")
def run_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return JSONResponse({"success": True, "snapshot": build_snapshot()})


@router.get("/preview")
def preview_daily_snapshot(current_user: CurrentUser = Depends(get_current_user)):
    return {"success": True, "data": build_snapshot()}
