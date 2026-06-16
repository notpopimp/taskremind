import os
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------- Request Models ----------
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

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    due_at: str | None = None
    recurrence: str = "none"
    priority: str = "medium"
    category: str = ""

class TaskToggle(BaseModel):
    completed_by: str | None = None

class TaskUpdate(BaseModel):
    description: str | None = None
    title: str | None = None

class NotePut(BaseModel):
    content: str = ""

# ---------- Database ----------
def get_db():
    url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    if url:
        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    else:
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
            completed_by TEXT DEFAULT '',
            recurrence TEXT DEFAULT 'none',
            created_at TEXT NOT NULL
        )
    """)
    # Add columns if upgrading
    for col, dtype in [("completed_by", "TEXT DEFAULT ''"), ("recurrence", "TEXT DEFAULT 'none'"),
                       ("priority", "TEXT DEFAULT 'medium'"), ("category", "TEXT DEFAULT ''")]:
        cur.execute(f"""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name='tasks' AND column_name='{col}'
        """)
        if cur.fetchone()["count"] == 0:
            cur.execute(f"ALTER TABLE tasks ADD COLUMN {col} {dtype}")
    # Notes table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            user_id TEXT NOT NULL REFERENCES users(id),
            date TEXT NOT NULL,
            content TEXT DEFAULT '',
            PRIMARY KEY (user_id, date)
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

# ---------- App Setup ----------
app = FastAPI(title="Task Reminder App")

BASE_DIR = Path(__file__).parent
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

jinja_env = Environment(
    loader=FileSystemLoader(str(BASE_DIR / "templates")),
    autoescape=select_autoescape(["html", "xml"]),
    cache_size=0,
)

class NoCacheTemplates:
    """Bypass Starlette's broken Jinja2Templates cache (Starlette 1.0.0 bug)."""
    def __init__(self, env):
        self.env = env
    def TemplateResponse(self, name, context):
        template = self.env.get_template(name)
        html = template.render(context)
        return HTMLResponse(html)

templates = NoCacheTemplates(jinja_env)

db_ready = False

@app.on_event("startup")
def startup():
    global db_ready
    try:
        init_db()
        db_ready = True
        print("Database OK")
    except Exception as e:
        print(f"Database not available: {e}")

@app.get("/_health")
def health():
    return {"status": "ok", "db": db_ready}

# ---------- Helpers ----------
def now_iso():
    return datetime.utcnow().isoformat()

def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()

def make_token():
    return secrets.token_hex(32)

SESSIONS: dict[str, str] = {}

def get_user(request: Request) -> str:
    token = request.cookies.get("session")
    uid = SESSIONS.get(token) if token else None
    if not uid:
        raise HTTPException(401, "Not logged in")
    return uid

# Recurrence patterns
def next_recurrence(due_at: str, pattern: str) -> str | None:
    if pattern == "none" or not due_at:
        return None
    dt = datetime.fromisoformat(due_at)
    if pattern == "daily":
        return (dt + timedelta(days=1)).isoformat()
    elif pattern == "weekly":
        return (dt + timedelta(weeks=1)).isoformat()
    elif pattern == "biweekly":
        return (dt + timedelta(weeks=2)).isoformat()
    elif pattern == "monthly":
        month = dt.month + 1
        year = dt.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(dt.day, [31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,31,30,31,30,31,31,30,31,30,31][month-1])
        return dt.replace(year=year, month=month, day=day).isoformat()
    elif pattern == "quarterly":
        month = dt.month + 3
        year = dt.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(dt.day, [31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,31,30,31,30,31,31,30,31,30,31][month-1])
        return dt.replace(year=year, month=month, day=day).isoformat()
    elif pattern == "yearly":
        return dt.replace(year=dt.year + 1).isoformat()
    return None

# ---------- Auth Routes ----------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if not db_ready:
        return HTMLResponse("""
        <html><body style="font-family:sans-serif;background:#f0f2f5;color:#1a1a2e;display:flex;align-items:center;justify-content:center;height:100vh">
        <div style="text-align:center">
            <h1 style="color:#4165e1">⏰ TaskRemind</h1>
            <p style="color:#e53935">Database not configured yet.</p>
            <p style="color:#98a2b3">Set <code>DATABASE_URL</code> in Railway Variables, then redeploy.</p>
        </div></body></html>
        """, status_code=200)
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

# ---------- Task Routes ----------
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
        "INSERT INTO tasks (id, user_id, title, description, due_at, completed, priority, category, recurrence, created_at) VALUES (%s,%s,%s,%s,%s,0,%s,%s,%s,%s) RETURNING *",
        (task_id, uid, body.title, body.description, body.due_at or None, body.priority, body.category, body.recurrence, now_iso()),
    )
    task = cur.fetchone()
    cur.close()
    conn.close()
    return dict(task)

@app.post("/api/tasks/{task_id}/toggle")
def toggle_task(request: Request, task_id: str, body: TaskToggle = None):
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
    completed_by = ""
    if new_val == 1 and body and body.completed_by:
        completed_by = body.completed_by
    cur.execute(
        "UPDATE tasks SET completed = %s, completed_by = %s WHERE id = %s",
        (new_val, completed_by, task_id),
    )
    # Recurring: create next occurrence
    next_id = None
    if new_val == 1 and task["recurrence"] not in (None, "none", ""):
        next_due = next_recurrence(task["due_at"], task["recurrence"])
        if next_due:
            next_id = uuid.uuid4().hex[:12]
            cur.execute(
                "INSERT INTO tasks (id, user_id, title, description, due_at, completed, priority, category, recurrence, created_at) VALUES (%s,%s,%s,%s,%s,0,%s,%s,%s,%s)",
                (next_id, uid, task["title"], task["description"], next_due, task.get("priority","medium"), task.get("category",""), task["recurrence"], now_iso()),
            )
    cur.close()
    conn.close()
    return {"ok": True, "completed": bool(new_val), "next_id": next_id}

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

@app.put("/api/tasks/{task_id}")
def update_task(request: Request, task_id: str, body: TaskUpdate):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE id = %s AND user_id = %s", (task_id, uid))
    task = cur.fetchone()
    if not task:
        cur.close()
        conn.close()
        raise HTTPException(404, "Task not found")
    if body.description is not None:
        cur.execute("UPDATE tasks SET description = %s WHERE id = %s", (body.description, task_id))
    if body.title is not None:
        cur.execute("UPDATE tasks SET title = %s WHERE id = %s", (body.title, task_id))
    cur.close()
    conn.close()
    return {"ok": True}

# ---------- Calendar Route ----------
@app.get("/api/tasks/calendar")
def calendar_tasks(request: Request):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM tasks WHERE user_id = %s AND completed = 0 AND due_at IS NOT NULL ORDER BY due_at ASC",
        (uid,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

# ---------- Notes Routes ----------
@app.get("/api/notes")
def list_note_dates(request: Request):
    """Return list of date strings that have notes for this user."""
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT date FROM notes WHERE user_id = %s AND content != ''", (uid,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r["date"] for r in rows]

@app.get("/api/notes/{date}")
def get_note(request: Request, date: str):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT content FROM notes WHERE user_id = %s AND date = %s", (uid, date))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return {"content": row["content"] if row else ""}

@app.put("/api/notes/{date}")
def save_note(request: Request, date: str, body: NotePut):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notes (user_id, date, content) VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id, date) DO UPDATE SET content = EXCLUDED.content",
        (uid, date, body.content),
    )
    cur.close()
    conn.close()
    return {"ok": True}

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

@app.get("/health")
def health():
    return {"status": "ok"}

# ---------- Export ----------
@app.get("/api/export/{fmt}")
def export_tasks(request: Request, fmt: str = "json"):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE user_id = %s ORDER BY created_at DESC", (uid,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    if fmt == "csv":
        import csv, io
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        else:
            buf.write("id,title,description,due_at,completed,completed_by,recurrence,created_at\n")
        return Response(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=tasks.csv"})
    return rows

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
