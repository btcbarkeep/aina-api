# Aina API — DB Starter (FastAPI + SQLModel + Postgres)

Minimal API with **Buildings** and **Events** endpoints.

## Endpoints
- `POST /buildings` — create building
- `GET /buildings/{id}` — fetch building
- `GET /buildings?limit=&offset=` — list buildings
- `POST /events` — create event (requires `building_id`)
- `GET /events?building_id=&unit_number=&limit=&offset=` — list events
- `GET /health` — health check

## Quick deploy (Render)
1. Create a Postgres (Neon/Render/DO) and copy **DATABASE_URL**.
   - If it starts with `postgres://`, change it to `postgresql+psycopg2://`
2. In Render → your Web Service → **Environment** → add:
   - `DATABASE_URL = postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME`
3. Click **Deploy latest**.

## Local test (optional)
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="sqlite:///./local.db"  # or your Postgres URL
uvicorn main:app --reload
```

## Example requests
Create a building:
```
curl -X POST https://api.ainaprotocol.com/buildings   -H 'content-type: application/json'   -d '{ "name":"Kaanapali Shores", "address":"3445 Lower Honoapiilani Rd", "city":"Lahaina", "state":"HI", "zip":"96761" }'
```

Create an event:
```
curl -X POST https://api.ainaprotocol.com/events   -H 'content-type: application/json'   -d '{ "building_id": 1, "unit_number":"264", "event_type":"notice", "title":"Plumbing maintenance", "body":"Shutoff 10–12am", "occurred_at":"2025-01-01T10:00:00Z" }'
```

List events for a building:
```
curl "https://api.ainaprotocol.com/events?building_id=1&limit=20"
```

---

**Note:** This auto-creates tables at startup (simple for MVP). Later we can add migrations (Alembic) and auth.
