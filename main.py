from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# DB bootstrap
from database import create_db_and_tables

# Routers
from routers import buildings, events, uploads, documents

# ---- Create the app ----
app = FastAPI(title="Aina API", version="0.2.0")

# ---- CORS ----
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://your-frontend-domain.com"  # replace with your actual frontend domain
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Include Routers ----
app.include_router(buildings.router, prefix="/buildings", tags=["Buildings"])
app.include_router(events.router, prefix="/events", tags=["Events"])
app.include_router(uploads.router, prefix="", tags=["Uploads"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])

# ---- Serve Uploaded Files ----
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ---- Root Route ----
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head><title>Aina API</title></head>
        <body style="font-family: sans-serif; margin: 2rem;">
            <h2>Aina Protocol API is running 🚀</h2>
            <p>Try POSTing to <code>/upload</code> with a file to test uploads.</p>
            <p>Uploaded files will be available at <code>/uploads/&lt;filename&gt;</code>.</p>
        </body>
    </html>
    """

# ---- Initialize DB on Startup ----
@app.on_event("startup")
def on_startup():
    create_db_and_tables()
