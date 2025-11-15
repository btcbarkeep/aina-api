# routers/admin_daily.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta

from dependencies.auth import get_current_user
from core.supabase_client import get_supabase_client
from core.notifications import send_email

router = APIRouter(
    prefix="/admin-daily",
    tags=["Admin Daily Update"],
)


# --------------------------------------------------------
# Helper — Fetch daily snapshot from Supabase
# --------------------------------------------------------
def get_daily_snapshot():
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    now = datetime.utcnow()
    since = now - timedelta(hours=24)

    snapshot = {}

    # Buildings
    buildings = (
        client.table("buildings")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )

    snapshot["buildings_total"] = len(buildings)
    snapshot["new_buildings"] = [
        b for b in buildings if b.get("created_at") and b["created_at"] >= since.isoformat()
    ]

    # Events
    events = (
        client.table("events")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )

    snapshot["events_total"] = len(events)
    snapshot["new_events"] = [
        e for e in events if e.get("created_at") and e["created_at"] >= since.isoformat()
    ]

    # Documents
    documents = (
        client.table("documents")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )

    snapshot["documents_total"] = len(documents)
    snapshot["new_documents"] = [
        d for d in documents if d.get("created_at") and d["created_at"] >= since.isoformat()
    ]

    snapshot["generated_at"] = now.isoformat()
    snapshot["time_range"] = f"{since.isoformat()} → {now.isoformat()}"

    return snapshot


# --------------------------------------------------------
# Helper — Format email nicely
# --------------------------------------------------------
def format_daily_email(snapshot: dict) -> str:
    lines = []
    lines.append("Aina Protocol — Daily System Update")
    lines.append("")
    lines.append(f"Date: {snapshot['generated_at']}")
    lines.append(f"Range: {snapshot['time_range']}")
    lines.append("")
    lines.append("=== Buildings ===")
    lines.append(f"Total Buildings: {snapshot['buildings_total']}")
    lines.append(f"New in last 24h: {len(snapshot['new_buildings'])}")
    for b in snapshot["new_buildings"]:
        lines.append(f" • {b['name']} ({b.get('city', '')}, {b.get('state', '')})")
    lines.append("")
    lines.append("=== Events ===")
    lines.append(f"Total Events: {snapshot['events_total']}")
    lines.append(f"New in last 24h: {len(snapshot['new_events'])}")
    for e in snapshot["new_events"]:
        lines.append(f" • {e.get('title', 'Untitled')} (building {e['building_id']})")
    lines.append("")
    lines.append("=== Documents ===")
    lines.append(f"Total Documents: {snapshot['documents_total']}")
    lines.append(f"New in last 24h: {len(snapshot['new_documents'])}")
    for d in snapshot["new_documents"]:
        lines.append(f" • {d['filename']} (event {d['event_id']})")
    lines.append("")
    lines.append("End of report.")

    return "\n".join(lines)


# --------------------------------------------------------
# POST — Trigger daily email manually
# --------------------------------------------------------
@router.post("/send", summary="Send today's admin daily report email")
def send_daily_update(current_user: dict = Depends(get_current_user)):
    snapshot = get_daily_snapshot()
    body = format_daily_email(snapshot)

    send_email(
        subject="Aina Protocol — Daily Update",
        body=body
    )

    return JSONResponse({
        "status": "sent",
        "snapshot": snapshot
    })


# --------------------------------------------------------
# GET — Preview daily report JSON
# --------------------------------------------------------
@router.get("/preview", summary="Preview today's daily report (JSON)")
def preview_daily_snapshot(current_user: dict = Depends(get_current_user)):
    return get_daily_snapshot()
