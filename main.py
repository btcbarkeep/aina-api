from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from database import create_db_and_tables
from routers import buildings, events, uploads, documents  # routers imported after app imports

app = FastAPI(title="Aina API", version="0.2.0")

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

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# include routers AFTER app exists
app.include_router(buildings.router)
app.include_router(events.router)
app.include_router(uploads.router)
app.include_router(documents.router)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def root():
    return "<h1>Aina API is running ✅</h1><p>Try <code>/health</code> or <code>/docs</code>.</p>"

