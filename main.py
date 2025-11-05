# main.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# DB bootstrap
from database import create_db_and_tables

# Routers (make sure these files exist under routers/)
#   routers/buildings.py
#   routers/events.py
#   routers/uploads.py
#   routers/documents.py
from routers import buildings, events, uploads, documents

# ---- Create the app FIRST ----
app = FastAPI(title="Aina API", version="0.2.0")

# CORS (origins you’ll use in browser)
ALLOWED_ORIGINS = [
    "https://app.ainaprotocol.com",
    "https://www.ainaprotocol.com",
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Ensure tables exist on boot
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# ---- Include routers AFTER app exists ----
app.include_router(buildings.router)
app.include_router(events.router)
app.include_router(uploads.router)     # POST /upload/url
app.include_router(documents.router)   # POST /documents/attach, GET /documents

# Health + root
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def root():
    return "<h1>Aina API is running ✅</h1><p>Try <code>/docs</code> or <code>/health</code>.</p>"
