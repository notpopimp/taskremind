import os
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# ---------- Request Models (JSON body, no python-multipart needed) ----------
class LoginRequest(BaseModel):
    username: str
    pin: str

class RegisterRequest(BaseModel):
    username: str
    pin: str

class ExtendRequest(BaseModel):
    hours: int = 1

class ShareRequest(BaseModel):
    permission: str = "view"

# ---------- Database ----------
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    # Local fallback if you have PostgreSQL running:
    # or comment out to use SQLite fallback via an in-memory mode
    # For now: use a small helper that wraps psycopg2
)

# We'll default to a local PostgreSQL or you can set DATABASE_URL
# Railway auto-injects DATABASE_URL when you add PostgreSQL.

conn_kwargs = {}

def get_db():
    url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    if url:
        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    else:
        # Local dev fallback: connect to a local PG instance
        conn = psycopg2.connect(
            dbname="taskapp",
            user="postgres",
            password="postgres",
            host="localhost",
            cursor_factory=RealDictCursor,
        )
    conn.autocommit = True
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            pin_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            due_at TEXT,
            completed INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS shares (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            permission TEXT NOT NULL DEFAULT 'view',
            created_at TEXT NOT NULL
        )
    """)
    cur.close()
    conn.close()

init_db()

# ---------- App Setup ----------
app = FastAPI(title="Task Reminder App")

BASE_DIR = Path(__file__).parent
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ---------- Helpers ----------
def now_iso():
    return datetime.utcnow().isoformat()

def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()

def make_token():
    return secrets.token_hex(32)

# In-memory sessions
SESSIONS: dict[str, str] = {}

# ---------- Auth Routes ----------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    token = request.cookies.get("session")
    user_id = SESSIONS.get(token) if token else None
    if not user_id:
        return templates.TemplateResponse("login.html", {"request": request})
    return templates.TemplateResponse("index.html", {"request": request, "user_id": user_id})

@app.post("/api/login")
def login(body: LoginRequest):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s", (body.username,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if user and user["pin_hash"] == hash_pin(body.pin):
        token = make_token()
        SESSIONS[token] = user["id"]
        resp = JSONResponse({"ok": True, "token": token, "user_id": user["id"]})
        resp.set_cookie(key="session", value=token, httponly=True, max_age=86400*30)
        return resp
    raise HTTPException(401, "Invalid username or PIN")

@app.post("/api/register")
def register(body: RegisterRequest):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = %s", (body.username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(409, "Username already taken")
    user_id = uuid.uuid4().hex[:12]
    cur.execute(
        "INSERT INTO users (id, username, pin_hash, created_at) VALUES (%s, %s, %s, %s)",
        (user_id, body.username, hash_pin(body.pin), now_iso()),
    )
    cur.close()
    conn.close()
    token = make_token()
    SESSIONS[token] = user_id
    resp = JSONResponse({"ok": True, "token": token, "user_id": user_id})
    resp.set_cookie(key="session", value=token, httponly=True, max_age=86400*30)
    return resp

@app.post("/api/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("session")
    return resp

def get_user(request: Request) -> str:
    token = request.cookies.get("session")
    uid = SESSIONS.get(token) if token else None
    if not uid:
        raise HTTPException(401, "Not logged in")
    return uid

# ---------- Task Routes ----------
class TaskCreate(BaseModel):
    title: str
    description: str = ""
    due_at: str | None = None

@app.get("/api/tasks")
def list_tasks(request: Request):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM tasks WHERE user_id = %s ORDER BY completed ASC, due_at ASC",
        (uid,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/tasks")
def create_task(request: Request, body: TaskCreate):
    uid = get_user(request)
    task_id = uuid.uuid4().hex[:12]
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (id, user_id, title, description, due_at, completed, created_at) VALUES (%s,%s,%s,%s,%s,0,%s) RETURNING *",
        (task_id, uid, body.title, body.description, body.due_at or None, now_iso()),
    )
    task = cur.fetchone()
    cur.close()
    conn.close()
    return dict(task)

@app.post("/api/tasks/{task_id}/toggle")
def toggle_task(request: Request, task_id: str):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE id = %s AND user_id = %s", (task_id, uid))
    task = cur.fetchone()
    if not task:
        cur.close()
        conn.close()
        raise HTTPException(404, "Task not found")
    new_val = 0 if task["completed"] else 1
    cur.execute("UPDATE tasks SET completed = %s WHERE id = %s", (new_val, task_id))
    cur.close()
    conn.close()
    return {"ok": True, "completed": bool(new_val)}

@app.delete("/api/tasks/{task_id}")
def delete_task(request: Request, task_id: str):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s AND user_id = %s", (task_id, uid))
    cur.close()
    conn.close()
    return {"ok": True}

@app.post("/api/tasks/{task_id}/extend")
def extend_task(request: Request, task_id: str, body: ExtendRequest = None):
    if body is None:
        body = ExtendRequest()
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE id = %s AND user_id = %s", (task_id, uid))
    task = cur.fetchone()
    if not task:
        cur.close()
        conn.close()
        raise HTTPException(404, "Task not found")
    old_due = task["due_at"]
    if old_due:
        new_due = (datetime.fromisoformat(old_due) + timedelta(hours=body.hours)).isoformat()
    else:
        new_due = (datetime.utcnow() + timedelta(hours=body.hours)).isoformat()
    cur.execute("UPDATE tasks SET due_at = %s, completed = 0 WHERE id = %s", (new_due, task_id))
    cur.close()
    conn.close()
    return {"ok": True, "due_at": new_due}

# ---------- Share Routes ----------
@app.post("/api/shares")
def create_share(request: Request, body: ShareRequest = None):
    if body is None:
        body = ShareRequest()
    uid = get_user(request)
    if body.permission not in ("view", "edit"):
        raise HTTPException(400, "Permission must be 'view' or 'edit'")
    share_id = uuid.uuid4().hex[:8]
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO shares (id, user_id, permission, created_at) VALUES (%s,%s,%s,%s)",
        (share_id, uid, body.permission, now_iso()),
    )
    cur.close()
    conn.close()
    return {"share_id": share_id, "url": f"/shared/{share_id}"}

@app.get("/api/shares")
def list_shares(request: Request):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shares WHERE user_id = %s ORDER BY created_at DESC", (uid,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

@app.delete("/api/shares/{share_id}")
def delete_share(request: Request, share_id: str):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM shares WHERE id = %s AND user_id = %s", (share_id, uid))
    cur.close()
    conn.close()
    return {"ok": True}

# ---------- Shared View ----------
@app.get("/shared/{share_id}", response_class=HTMLResponse)
def shared_view(request: Request, share_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shares WHERE id = %s", (share_id,))
    share = cur.fetchone()
    if not share:
        cur.close()
        conn.close()
        return HTMLResponse("Not found", status_code=404)
    cur.execute(
        "SELECT * FROM tasks WHERE user_id = %s ORDER BY completed ASC, due_at ASC",
        (share["user_id"],),
    )
    tasks = cur.fetchall()
    cur.execute("SELECT username FROM users WHERE id = %s", (share["user_id"],))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return templates.TemplateResponse("shared.html", {
        "request": request,
        "share_id": share_id,
        "permission": share["permission"],
        "username": user["username"] if user else "Unknown",
        "tasks": [dict(t) for t in tasks],
    })

# ---------- API for shared tasks ----------
@app.get("/api/shared/{share_id}/tasks")
def get_shared_tasks(share_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shares WHERE id = %s", (share_id,))
    share = cur.fetchone()
    if not share:
        cur.close()
        conn.close()
        raise HTTPException(404, "Share not found")
    cur.execute(
        "SELECT * FROM tasks WHERE user_id = %s ORDER BY completed ASC, due_at ASC",
        (share["user_id"],),
    )
    tasks = cur.fetchall()
    cur.close()
    conn.close()
    return {"permission": share["permission"], "tasks": [dict(t) for t in tasks]}

@app.post("/api/shared/{share_id}/tasks/{task_id}/toggle")
def toggle_shared_task(share_id: str, task_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shares WHERE id = %s", (share_id,))
    share = cur.fetchone()
    if not share:
        cur.close()
        conn.close()
        raise HTTPException(404, "Share not found")
    if share["permission"] != "edit":
        cur.close()
        conn.close()
        raise HTTPException(403, "View-only share")
    cur.execute("SELECT * FROM tasks WHERE id = %s AND user_id = %s", (task_id, share["user_id"]))
    task = cur.fetchone()
    if not task:
        cur.close()
        conn.close()
        raise HTTPException(404, "Task not found")
    new_val = 0 if task["completed"] else 1
    cur.execute("UPDATE tasks SET completed = %s WHERE id = %s", (new_val, task_id))
    cur.close()
    conn.close()
    return {"ok": True, "completed": bool(new_val)}

# ---------- Reminder Check ----------
@app.get("/api/reminders")
def check_reminders(request: Request):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    now = now_iso()
    cur.execute(
        "SELECT * FROM tasks WHERE user_id = %s AND completed = 0 AND due_at IS NOT NULL AND due_at < %s ORDER BY due_at ASC",
        (uid, now),
    )
    overdue = cur.fetchall()
    soon_deadline = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    cur.execute(
        "SELECT * FROM tasks WHERE user_id = %s AND completed = 0 AND due_at IS NOT NULL AND due_at > %s AND due_at < %s ORDER BY due_at ASC",
        (uid, now, soon_deadline),
    )
    soon = cur.fetchall()
    cur.close()
    conn.close()
    return {"overdue": [dict(t) for t in overdue], "soon": [dict(t) for t in soon]}

# ---------- Health Check (Railway uses this) ----------
@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
