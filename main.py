from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Aina API", version="0.1.0")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def root():
    return "<h1>Aina API is running ✅</h1><p>Try <code>/health</code>.</p>"
