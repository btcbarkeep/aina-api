import sys
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# Ensure 'src' is recognized as a package (important for Render)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ---- Database ----
from src.database import create_db_and_tables


import sys, os
print("=== PYTHONPATH ===")
for p in sys.path:
    print(" ", p)
print("=== CWD:", os.getcwd(), "===")
try:
    import dependencies
    print("Imported dependencies:", dependencies.__file__)
except Exception as e:
    print("⚠️ Could not import bare 'dependencies':", e)
try:
    import src.dependencies as dep2
    print("Imported src.dependencies:", dep2.__file__)
except Exception as e:
    print("⚠️ Could not import src.dependencies:", e)



# ---- Routers ----
from src.routers import buildings, events, documents, uploads, auth

# ---- Create the FastAPI app ----
app = FastAPI(
    title="Aina Protocol API",
    version="0.3.0",
    description="Backend for Aina Protocol — blockchain-based condo and property reporting system."
)

# ---- CORS Configuration ----
# You can expand this list later with your frontend domain
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
# Each router already defines its prefix and tags
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

@app.get("/")
def health_check():
    return {"status": "ok"}
