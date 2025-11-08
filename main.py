import os
import sys
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# ✅ Ensure 'src' is recognized as a package for local + Render
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

# ---- Database ----
from src.database import create_db_and_tables

# ---- Routers ----
from src.routers import buildings, events, documents, uploads, auth

# ---- Create the FastAPI app ----
app = FastAPI(
    title="Aina Protocol API",
    version="0.3.0",
    description="Backend for Aina Protocol — blockchain-based condo and property reporting system."
)

# ---- CORS Configuration ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://your-frontend-domain.com",  # Replace with your actual frontend domain
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Initialize Database on Startup ----
@app.on_event("startup")
def on_startup():
    """Initialize database tables when the app starts."""
    create_db_and_tables()

# ---- Include Routers ----
# Each router defines its own prefix and tags
app.include_router(auth.router)
app.include_router(buildings.router)
app.include_router(events.router)
app.include_router(documents.router)
app.include_router(uploads.router)

# ---- Root Route ----
@app.get("/", response_class=HTMLResponse)
async def root():
    """Landing page for the API."""
    return """
    <html>
        <head><title>Aina Protocol API</title></head>
        <body style="font-family: sans-serif; margin: 2rem;">
            <h2>🌺 Aina Protocol API is running 🚀</h2>
            <ul>
                <li>✅ <b>Uploads</b> working via <code>/upload</code></li>
                <li>✅ <b>Explore full API docs</b> at <a href='/docs' target='_blank'>/docs</a></li>
                <li>✅ <b>Routers active:</b> Buildings, Events, Documents, Uploads, and Auth</li>
            </ul>
        </body>
    </html>
    """

# ---- Health Check ----
@app.get("/health")
def health_check():
    return {"status": "ok"}
