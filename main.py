from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Aina API", version="0.1.0")

from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = [
    "https://app.ainaprotocol.com",
    "https://www.ainaprotocol.com",
    # For local testing (optional):
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


@app.get("/health")
def health():
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def root():
    return "<h1>Aina API is running ✅</h1><p>Try <code>/health</code>.</p>"
