from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# Database
from database import create_db_and_tables

# Routers
from routers import buildings, events, uploads, documents

# ---- Create the app ----
app = FastAPI(title="Aina API", version="0.2.0")

# ---- CORS Configuration ----
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://your-frontend-domain.com"  # Replace with your real frontend domain
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Include Routers ----
# Each router is mounted once with a clear prefix and tag
app.include_router(buildings.router, prefix="/buildings", tags=["Buildings"])
app.include_router(events.router, prefix="/events", tags=["Events"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(uploads.router, prefix="", tags=["Uploads"])  # keep root-level upload

# ---- Root Route ----
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head><title>Aina Protocol API</title></head>
        <body style="font-family: sans-serif; margin: 2rem;">
            <h2>Aina Protocol API is running 🚀</h2>
            <p>✅ Uploads working via <code>/upload</code></p>
            <p>✅ Explore full API docs at <a href='/docs' target='_blank'>/docs</a></p>
            <p>✅ Buildings, Events, and Documents all use structured endpoints.</p>
        </body>
    </html>
    """

# ---- Initialize DB on Startup ----
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

from routers import buildings, events, uploads, documents, auth

from routers import auth
app.include_router(auth.router)

