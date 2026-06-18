import os
import uuid
import hashlib
import secrets
import json
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
    hours: float = 1.0

class ShareRequest(BaseModel):
    permission: str = "view"

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    due_at: str | None = None
    recurrence: str = "none"
    priority: str = "medium"
    category: str = ""
    start_at: str | None = None
    is_reminder: bool = False
    end_at: str | None = None
    remind_before: int = 0

class TaskToggle(BaseModel):
    completed_by: str | None = None

class TaskUpdate(BaseModel):
    description: str | None = None
    title: str | None = None
    due_at: str | None = None
    recurrence: str | None = None
    priority: str | None = None
    category: str | None = None
    start_at: str | None = None
    is_reminder: bool | None = None
    end_at: str | None = None
    remind_before: int | None = None

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
            created_at TEXT NOT NULL,
            role TEXT DEFAULT 'user'
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
                       ("priority", "TEXT DEFAULT 'medium'"), ("category", "TEXT DEFAULT ''"),
                       ("is_reminder", "INTEGER DEFAULT 0"), ("end_at", "TEXT DEFAULT NULL"),
                       ("start_at", "TEXT DEFAULT NULL"), ("remind_before", "INTEGER DEFAULT 0"),
                       ("last_reminded_at", "TEXT DEFAULT NULL"), ("in_progress", "INTEGER DEFAULT 0")]:
        cur.execute(f"""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name='tasks' AND column_name='{col}'
        """)
        if cur.fetchone()["count"] == 0:
            cur.execute(f"ALTER TABLE tasks ADD COLUMN {col} {dtype}")
    # Push subscriptions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS push_subs (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            endpoint TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, endpoint)
        )
    """)
    # Add user columns if upgrading
    for col, dtype in [("role", "TEXT DEFAULT 'user'"),
                       ("phone", "TEXT DEFAULT ''"), ("email", "TEXT DEFAULT ''"),
                       ("categories", "TEXT DEFAULT '{}'")]:
        cur.execute(f"""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name='users' AND column_name='{col}'
        """)
        if cur.fetchone()["count"] == 0:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
            if col == "role":
                # First-time role column: set first registered user as admin
                cur.execute("UPDATE users SET role = 'admin' WHERE id = (SELECT id FROM users ORDER BY created_at ASC LIMIT 1)")
    # Set first user as admin if no admin exists
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'admin'")
    admin_count = cur.fetchone()["cnt"]
    if admin_count == 0:
        cur.execute("UPDATE users SET role = 'admin' WHERE id = (SELECT id FROM users ORDER BY created_at ASC LIMIT 1)")
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

# Serve service worker from root so it has correct scope
sw_path = static_dir / "service-worker.js"
if sw_path.exists():
    sw_content = sw_path.read_text()
    @app.get("/service-worker.js")
    def service_worker():
        return Response(content=sw_content, media_type="application/javascript", headers={"Cache-Control": "no-cache"})

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

def get_user_role(uid: str) -> str:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE id = %s", (uid,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row["role"] if row else "user"

def require_admin(uid: str):
    if get_user_role(uid) != "admin":
        raise HTTPException(403, "Only admin can perform this action")

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
            <h1 style="color:#4165e1">🧭 Waypoint</h1>
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
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    count = cur.fetchone()["cnt"]
    role = "admin" if count == 0 else "user"
    cur.execute(
        "INSERT INTO users (id, username, pin_hash, created_at, role) VALUES (%s, %s, %s, %s, %s)",
        (user_id, body.username, hash_pin(body.pin), now_iso(), role),
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

@app.get("/api/me")
def whoami(request: Request):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, phone, email, categories FROM users WHERE id = %s", (uid,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user:
        raise HTTPException(404, "User not found")
    ud = dict(user)
    try:
        ud["categories"] = json.loads(ud.get("categories", "{}"))
    except:
        ud["categories"] = {}
    return ud

@app.get("/api/me/promote")
def promote_to_admin(request: Request):
    """First-time setup: promote the current user to admin."""
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role='admin'", ())
    admin_count = cur.fetchone()["cnt"]
    if admin_count > 0:
        cur.close()
        conn.close()
        raise HTTPException(400, "An admin already exists")
    cur.execute("UPDATE users SET role='admin' WHERE id = %s", (uid,))
    cur.close()
    conn.close()
    return {"ok": True}

@app.put("/api/profile")
def update_profile(request: Request, body: dict):
    uid = get_user(request)
    phone = body.get("phone", "")
    email = body.get("email", "")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET phone = %s, email = %s WHERE id = %s", (phone, email, uid))
    cur.close()
    conn.close()
    return {"ok": True}

# ---------- User Categories ----------
DEFAULT_CATEGORIES = ["Personal", "Work", "Chores", "Health", "Scheduled", "Time Off", "Call Offs"]

def parse_cats(raw):
    """Parse categories JSON string to list."""
    if not raw:
        return None
    try:
        val = json.loads(raw)
        if isinstance(val, list) and all(isinstance(x, str) for x in val):
            return val
    except:
        pass
    return None

@app.get("/api/categories")
def get_categories(request: Request):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT categories FROM users WHERE id = %s", (uid,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(404, "User not found")
    cats = parse_cats(row["categories"])
    if cats is None:
        # Migration: if old format (dict), convert to sorted list of labels
        try:
            old = json.loads(row["categories"]) if row["categories"] else {}
            if isinstance(old, dict):
                cats = sorted(old.values())
            else:
                cats = list(DEFAULT_CATEGORIES)
        except:
            cats = list(DEFAULT_CATEGORIES)
    # Fallback if empty
    if not cats:
        cats = list(DEFAULT_CATEGORIES)
    return {"categories": cats}

@app.put("/api/categories")
def update_categories(request: Request, body: dict):
    uid = get_user(request)
    if not isinstance(body, dict) or "categories" not in body:
        raise HTTPException(400, "Body must have a 'categories' key")
    cats = body["categories"]
    if not isinstance(cats, list) or not all(isinstance(x, str) for x in cats):
        raise HTTPException(400, "categories must be an array of strings")
    if len(cats) > 10:
        raise HTTPException(400, "Maximum 10 categories allowed")
    # Remove empty strings
    cats = [c.strip() for c in cats if c.strip()]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET categories = %s WHERE id = %s", (json.dumps(cats), uid))
    cur.close()
    conn.close()
    return {"categories": cats}

@app.post("/api/push/subscribe")
def push_subscribe(request: Request, body: dict):
    uid = get_user(request)
    endpoint = body.get("endpoint", "")
    keys = body.get("keys", {})
    conn = get_db()
    cur = conn.cursor()
    now = now_iso()
    cur.execute(
        "INSERT INTO push_subs (user_id, endpoint, p256dh, auth, created_at) VALUES (%s,%s,%s,%s,%s) "
        "ON CONFLICT (user_id, endpoint) DO UPDATE SET p256dh=EXCLUDED.p256dh, auth=EXCLUDED.auth",
        (uid, endpoint, keys.get("p256dh",""), keys.get("auth",""), now),
    )
    cur.close()
    conn.close()
    return {"ok": True}

@app.get("/api/push/vapid")
def get_vapid_public_key():
    """Return VAPID public key from env or a placeholder."""
    key = os.environ.get("VAPID_PUBLIC_KEY", "")
    return {"publicKey": VAPID_PUBLIC_KEY}

# CRON_SECRET for push notification scheduler
CRON_SECRET_VAL = os.environ.get("CRON_SECRET")
if CRON_SECRET_VAL:
    CRON_SECRET = CRON_SECRET_VAL
else:
    CRON_SECRET = "taskremind-cron-secret-2026"
    print("CRON_SECRET not set in env, using hardcoded default")

# ---------- VAPID Keys (auto-generate if missing) ----------
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")

if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        import base64
        key = ec.generate_private_key(ec.SECP256R1())
        priv_raw = key.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
        )
        pub_raw = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        VAPID_PRIVATE_KEY = base64.urlsafe_b64encode(priv_raw).rstrip(b"=").decode()
        VAPID_PUBLIC_KEY = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
        print(f"Auto-generated VAPID keys. Set VAPID_PUBLIC_KEY={VAPID_PUBLIC_KEY} in Railway env for persistence.")
    except Exception as e:
        print(f"Could not generate VAPID keys: {e}")

# ---------- Email / SMS Notifications ----------
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "waypoint.notifications@gmail.com")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")

def send_email(to_email: str, subject: str, body: str) -> tuple:
    """Send email via SendGrid HTTP API. Returns (True, '') on success or (False, error_msg)."""
    if not SENDGRID_API_KEY or not to_email:
        return (False, "Missing SENDGRID_API_KEY or recipient email")
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        message = Mail(
            from_email=SENDGRID_FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            plain_text_content=body)
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        if response.status_code in (200, 201, 202):
            return (True, "")
        else:
            return (False, f"SendGrid HTTP {response.status_code}")
    except Exception as e:
        err = str(e)
        print(f"Email send error: {err}")
        return (False, err)

def send_sms(to_phone: str, body: str) -> bool:
    """Send SMS via Twilio. Returns True on success."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER or not to_phone:
        return False
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(body=body, from_=TWILIO_PHONE_NUMBER, to=to_phone)
        return True
    except Exception as e:
        print(f"SMS send error: {e}")
        return False

@app.get("/api/cron/check-reminders")
@app.post("/api/cron/check-reminders")
def cron_check_reminders(request: Request):
    """Called by Railway cron: sends push notifications for due reminders."""
    auth = request.query_params.get("secret", "")
    if not CRON_SECRET or auth != CRON_SECRET:
        raise HTTPException(401, "Invalid cron secret")

    vapid_private = VAPID_PRIVATE_KEY
    vapid_public = VAPID_PUBLIC_KEY
    if not vapid_private or not vapid_public:
        return {"sent": 0, "error": "VAPID keys not configured"}

    try:
        now = datetime.utcnow()
        now_naive = now
        conn = get_db()
        cur = conn.cursor()

        # Get all users
        cur.execute("SELECT id, email, phone FROM users")
        users = cur.fetchall()

        push_sent = 0
        email_sent = 0
        sms_sent = 0
        for u in users:
            uid = u["id"]
            now_iso_str = now.isoformat()

            # Get tasks that need reminding
            cur.execute(
                """SELECT id, title, due_at, remind_before, last_reminded_at FROM tasks
                   WHERE user_id = %s AND completed = 0 AND due_at IS NOT NULL
                   ORDER BY due_at ASC""",
                (uid,),
            )
            all_tasks = cur.fetchall()

            lines = []
            for t in all_tasks:
                try:
                    due = datetime.fromisoformat(t["due_at"])
                    if due.tzinfo is not None:
                        due = due.replace(tzinfo=None)
                except:
                    continue

                remind_before = t.get("remind_before", 0) or 0
                alert_time = due - timedelta(minutes=remind_before)
                last_reminded = t.get("last_reminded_at")

                should_remind = False
                is_realert = False

                if last_reminded is None:
                    if now >= alert_time:
                        should_remind = True
                elif now > due:
                    try:
                        last_dt = datetime.fromisoformat(last_reminded)
                        if last_dt.tzinfo is not None:
                            last_dt = last_dt.replace(tzinfo=None)
                    except:
                        continue

                    mins_since_last = (now - last_dt).total_seconds() / 60.0
                    mins_overdue = (now - due).total_seconds() / 60.0

                    if mins_overdue < 60:
                        interval = 30
                    elif mins_overdue < 240:
                        interval = 60
                    elif mins_overdue < 1440:
                        interval = 240
                    else:
                        interval = 1440

                    if mins_since_last >= interval:
                        should_remind = True
                        is_realert = True

                if should_remind:
                    try:
                        dt_str = due.strftime("%a %I:%M %p").lstrip("0")
                    except:
                        dt_str = t["due_at"][:16]

                    prefix = ""
                    if is_realert:
                        prefix = "⏰ STILL DUE: "
                    elif remind_before > 0:
                        if remind_before >= 10080:
                            prefix = "[1 week early] "
                        elif remind_before >= 4320:
                            prefix = "[3 days early] "
                        elif remind_before >= 1440:
                            prefix = "[1 day early] "
                        elif remind_before >= 60:
                            prefix = "[1 hour early] "

                    lines.append(f"{prefix}{dt_str} - {t['title'][:50]}")

                    cur.execute(
                        "UPDATE tasks SET last_reminded_at = %s WHERE id = %s",
                        (now_iso_str, t["id"]),
                    )

            if not lines:
                continue

            payload = {
                "title": "🧭 Waypoint Reminders",
                "body": "\n".join(lines),
            }

            text_body = "\n".join(lines) + "\n\n— Waypoint —\nReminder messages via telephone/email. Cancel or remove anytime."

            cur.execute(
                "SELECT endpoint, p256dh, auth FROM push_subs WHERE user_id = %s",
                (uid,),
            )
            subs = cur.fetchall()

            for sub in subs:
                try:
                    from pywebpush import webpush

                    sub_info = {
                        "endpoint": sub["endpoint"],
                        "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                    }
                    webpush(
                        subscription_info=sub_info,
                        data=json.dumps(payload),
                        vapid_private_key=vapid_private,
                        vapid_claims={"sub": "mailto:cagesliquidators@yahoo.com"},
                    )
                    push_sent += 1
                except Exception as e:
                    if "410" in str(e) or "expired" in str(e).lower():
                        cur.execute(
                            "DELETE FROM push_subs WHERE endpoint = %s",
                            (sub["endpoint"],),
                        )
                    continue

            if u["email"] and SENDGRID_API_KEY:
                ok, _ = send_email(u["email"], "🧭 Waypoint Reminders", text_body)
                if ok:
                    email_sent += 1

            if u["phone"] and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
                sms_body = "\n".join(lines)[:140]
                if len(sms_body) > 100:
                    sms_body += "\n-Cancel/remove anytime"
                if send_sms(u["phone"], sms_body):
                    sms_sent += 1

        cur.close()
        conn.close()
        return {"push_sent": push_sent, "email_sent": email_sent, "sms_sent": sms_sent, "checked_users": len(users)}
    except Exception as e:
        return {"error": str(e)}

# ---------- Task Routes ----------
@app.get("/api/tasks")
def list_tasks(request: Request):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT *, CASE WHEN in_progress=1 THEN 0 WHEN completed=0 THEN 1 ELSE 2 END as sort_order FROM tasks WHERE user_id = %s ORDER BY sort_order ASC, due_at ASC",
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
        "INSERT INTO tasks (id, user_id, title, description, due_at, completed, in_progress, priority, category, recurrence, created_at, is_reminder, end_at, start_at, remind_before) VALUES (%s,%s,%s,%s,%s,0,0,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (task_id, uid, body.title, body.description, body.due_at or None, body.priority, body.category, body.recurrence, now_iso(), int(body.is_reminder), body.end_at or None, body.start_at or None, body.remind_before),
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
    
    cur_status = "in_progress" if task.get("in_progress") else ("completed" if task["completed"] else "pending")
    
    if cur_status == "pending":
        # Pending → In Progress
        cur.execute("UPDATE tasks SET in_progress = 1, completed = 0, completed_by = '' WHERE id = %s", (task_id,))
        new_status = "in_progress"
    elif cur_status == "in_progress":
        # In Progress → Completed
        completed_by = ""
        if body and body.completed_by:
            completed_by = body.completed_by
        cur.execute("UPDATE tasks SET in_progress = 0, completed = 1, completed_by = %s WHERE id = %s", (completed_by, task_id))
        new_status = "completed"
    else:
        # Completed → Pending
        cur.execute("UPDATE tasks SET completed = 0, in_progress = 0, completed_by = '' WHERE id = %s", (task_id,))
        new_status = "pending"
    
    # Recurring: create next occurrence
    next_id = None
    if new_status == "completed" and task["recurrence"] not in (None, "none", ""):
        next_due = next_recurrence(task["due_at"], task["recurrence"])
        if next_due:
            next_id = uuid.uuid4().hex[:12]
            cur.execute(
                "INSERT INTO tasks (id, user_id, title, description, due_at, completed, in_progress, priority, category, recurrence, created_at) VALUES (%s,%s,%s,%s,%s,0,0,%s,%s,%s,%s)",
                (next_id, uid, task["title"], task["description"], next_due, task.get("priority", "medium"), task.get("category", ""), task["recurrence"], now_iso()),
            )
    cur.close()
    conn.close()
    return {"ok": True, "status": new_status, "next_id": next_id}

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
    if body.title is not None:
        cur.execute("UPDATE tasks SET title = %s WHERE id = %s", (body.title, task_id))
    if body.description is not None:
        cur.execute("UPDATE tasks SET description = %s WHERE id = %s", (body.description, task_id))
    if body.due_at is not None:
        cur.execute("UPDATE tasks SET due_at = %s WHERE id = %s", (body.due_at or None, task_id))
    if body.recurrence is not None:
        cur.execute("UPDATE tasks SET recurrence = %s WHERE id = %s", (body.recurrence, task_id))
    if body.priority is not None:
        cur.execute("UPDATE tasks SET priority = %s WHERE id = %s", (body.priority, task_id))
    if body.category is not None:
        cur.execute("UPDATE tasks SET category = %s WHERE id = %s", (body.category, task_id))
    if body.start_at is not None:
        cur.execute("UPDATE tasks SET start_at = %s WHERE id = %s", (body.start_at or None, task_id))
    if body.is_reminder is not None:
        cur.execute("UPDATE tasks SET is_reminder = %s WHERE id = %s", (int(body.is_reminder), task_id))
    if body.end_at is not None:
        cur.execute("UPDATE tasks SET end_at = %s WHERE id = %s", (body.end_at or None, task_id))
    if body.remind_before is not None:
        cur.execute("UPDATE tasks SET remind_before = %s WHERE id = %s", (body.remind_before, task_id))
    if body.title is not None and body.title.strip() == '':
        cur.execute("UPDATE tasks SET title = %s WHERE id = %s", ('', task_id))
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
        "SELECT * FROM tasks WHERE user_id = %s AND (completed = 0 OR is_reminder = 1) AND due_at IS NOT NULL ORDER BY due_at ASC",
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

@app.get("/api/db/push_subs_count")
def push_subs_count():
    """Debug: return count of push subscriptions."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM push_subs")
    cnt = cur.fetchone()["cnt"]
    cur.close()
    conn.close()
    return {"count": cnt}

@app.get("/api/stats")
def get_stats(request: Request):
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    
    now_str = datetime.utcnow().isoformat()
    
    # Current user stats
    cur.execute(
        "SELECT COUNT(*) as total, COALESCE(SUM(CASE WHEN completed=1 THEN 1 ELSE 0 END), 0) as done FROM tasks WHERE user_id = %s",
        (uid,),
    )
    user_stats = dict(cur.fetchone())
    
    # All users stats
    cur.execute(
        "SELECT COUNT(*) as total, COALESCE(SUM(CASE WHEN completed=1 THEN 1 ELSE 0 END), 0) as done FROM tasks"
    )
    overall_stats = dict(cur.fetchone())
    
    # Per-user breakdown
    cur.execute("""
        SELECT u.username, u.id,
               COUNT(t.id) as total,
               COALESCE(SUM(CASE WHEN t.completed=1 THEN 1 ELSE 0 END), 0) as done,
               COALESCE(SUM(CASE WHEN t.completed=0 AND t.due_at IS NOT NULL AND t.due_at < %s THEN 1 ELSE 0 END), 0) as overdue
        FROM users u
        LEFT JOIN tasks t ON t.user_id = u.id
        GROUP BY u.id, u.username
        ORDER BY u.username
    """, (now_str,))
    per_user = [dict(r) for r in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    return {
        "user": user_stats,
        "overall": overall_stats,
        "per_user": per_user,
    }

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
        "SELECT *, CASE WHEN in_progress=1 THEN 0 WHEN completed=0 THEN 1 ELSE 2 END as sort_order FROM tasks WHERE user_id = %s ORDER BY sort_order ASC, due_at ASC",
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
    share = _get_share_or_404(share_id)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT *, CASE WHEN in_progress=1 THEN 0 WHEN completed=0 THEN 1 ELSE 2 END as sort_order FROM tasks WHERE user_id = %s ORDER BY sort_order ASC, due_at ASC",
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
    if task.get("in_progress"):
        # In Progress → Completed
        cur.execute("UPDATE tasks SET in_progress = 0, completed = 1 WHERE id = %s", (task_id,))
    elif task["completed"]:
        # Completed → Pending
        cur.execute("UPDATE tasks SET completed = 0, in_progress = 0 WHERE id = %s", (task_id,))
    else:
        # Pending → In Progress
        cur.execute("UPDATE tasks SET in_progress = 1, completed = 0 WHERE id = %s", (task_id,))
    cur.close()
    conn.close()
    return {"ok": True}

def _get_share_or_404(share_id):
    """Helper: fetch share row or raise 404."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shares WHERE id = %s", (share_id,))
    share = cur.fetchone()
    cur.close()
    conn.close()
    if not share:
        raise HTTPException(404, "Share not found")
    return share

def _require_edit(share):
    if share["permission"] != "edit":
        raise HTTPException(403, "View-only share")

@app.post("/api/shared/{share_id}/tasks")
def create_shared_task(share_id: str, body: TaskCreate = None):
    share = _get_share_or_404(share_id)
    _require_edit(share)
    if body is None:
        body = TaskCreate()
    uid = share["user_id"]
    task_id = uuid.uuid4().hex[:12]
    now = now_iso()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (id, user_id, title, description, due_at, completed, priority, category, recurrence, created_at, is_reminder, end_at, start_at) VALUES (%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (task_id, uid, body.title, body.description, body.due_at or None, body.priority, body.category, body.recurrence, now, int(body.is_reminder), body.end_at or None, body.start_at or None),
    )
    task = cur.fetchone()
    cur.close()
    conn.close()
    return dict(task)

@app.put("/api/shared/{share_id}/tasks/{task_id}")
def update_shared_task(share_id: str, task_id: str, body: TaskUpdate = None):
    share = _get_share_or_404(share_id)
    _require_edit(share)
    if body is None:
        return {"ok": True}
    uid = share["user_id"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE id = %s AND user_id = %s", (task_id, uid))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(404, "Task not found")
    updates = {}
    for field in ["title", "description", "due_at", "recurrence", "priority", "category", "start_at", "end_at", "is_reminder"]:
        val = getattr(body, field, None)
        if val is not None:
            updates[field] = val
    if updates:
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        vals = list(updates.values()) + [task_id, uid]
        cur.execute(f"UPDATE tasks SET {set_clause} WHERE id = %s AND user_id = %s", vals)
    cur.close()
    conn.close()
    return {"ok": True}

@app.get("/api/shared/{share_id}/me")
def shared_me(share_id: str):
    """Return shared user info for the viewing page."""
    share = _get_share_or_404(share_id)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT username, categories FROM users WHERE id = %s", (share["user_id"],))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user:
        raise HTTPException(404, "User not found")
    # Parse categories
    try:
        cats = json.loads(user["categories"]) if user["categories"] else []
        if isinstance(cats, dict):
            cats = sorted(cats.values())
        elif not isinstance(cats, list):
            cats = list(DEFAULT_CATEGORIES)
        if not cats:
            cats = list(DEFAULT_CATEGORIES)
    except:
        cats = list(DEFAULT_CATEGORIES)
    return {"username": user["username"], "categories": cats, "permission": share["permission"]}

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

# ---------- Test Notification ----------
@app.post("/api/test-notification")
def test_notification(request: Request):
    """Send a test email/SMS to the current user."""
    uid = get_user(request)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT email, phone FROM users WHERE id = %s", (uid,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user:
        raise HTTPException(404, "User not found")
    results = []
    if user["email"] and SENDGRID_API_KEY:
        ok, err = send_email(user["email"], "🧭 Waypoint Test Notification", "This is a test reminder message via email. You can cancel or remove at any time.\n\n— Waypoint")
        if ok:
            results.append("email sent")
        else:
            results.append(f"email failed: {err[:120]}")
    else:
        results.append("email skipped (no email set or SendGrid not configured)")
    if user["phone"] and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
        if send_sms(user["phone"], "Waypoint test reminder. Cancel or remove anytime."):
            results.append("sms sent")
        else:
            results.append("sms failed")
    else:
        results.append("sms skipped (no phone set or Twilio not configured)")
    return {"status": ", ".join(results)}

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
