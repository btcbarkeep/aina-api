# Aina API — FastAPI Starter (for Render)

This is a tiny FastAPI app you can deploy to **Render**.

## What's inside
- `main.py` — the FastAPI app (routes: `/` and `/health`)
- `requirements.txt` — Python dependencies
- `render.yaml` — Render blueprint (optional; Render can also infer settings)
- `.gitignore` — keeps your repo clean

## Deploy in 10 minutes

### 1) Create a GitHub account (if you don't have one)
- Go to https://github.com/signup and create an account.
- Confirm your email.

### 2) Create a new repository
- Click the **+** (top-right) → **New repository**.
- Name it, e.g., `aina-api` → **Create repository**.
- Click **"uploading an existing file"**, then drag these files in:
  - `main.py`, `requirements.txt`, `render.yaml`, `.gitignore`, `README.md`
- Click **Commit changes**.

### 3) Deploy on Render
- Sign up / Log in: https://render.com/signup
- Click **New +** → **Web Service**.
- Connect your GitHub and pick the repo you just created.
- Render will detect Python.
  - **Build command:** `pip install -r requirements.txt`
  - **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
  - **Environment:** Python (use `PYTHON_VERSION=3.11.9` if asked)
- Click **Create Web Service** and wait for deploy.

When it finishes, visit your Render URL, e.g. `https://aina-api.onrender.com`
- `GET /` should show “Aina API is running ✅”
- `GET /health` should return `{ "ok": true }`

### 4) Point your domain (when ready)
In Cloudflare → **DNS → Add record**:
- `CNAME` **api** → `your-service-name.onrender.com` (Proxied)
- `CNAME` **app** → (later, when you deploy your dashboard)

You're deployed! Next step would be adding a database and your first endpoints.
