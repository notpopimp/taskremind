import urllib.request, urllib.error, json, http.cookiejar

BASE = "https://web-production-2b7e.up.railway.app"

for user in ["Ben", "Rachel", "Sam"]:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    
    # Login
    data = json.dumps({"username": user, "pin": "0000"}).encode()
    req = urllib.request.Request(f"{BASE}/api/login", data=data,
        headers={"Content-Type": "application/json"})
    try:
        resp = opener.open(req, timeout=10)
        login = json.loads(resp.read())
        print(f"{user}: Login OK")
    except Exception as e:
        print(f"{user}: Login failed - {e}")
        continue

    # Check reminders
    try:
        resp2 = opener.open(f"{BASE}/api/reminders", timeout=10)
        reminders = json.loads(resp2.read())
        overdue = reminders.get("overdue", [])
        soon = reminders.get("soon", [])
        print(f"  Overdue: {len(overdue)}, Due soon: {len(soon)}")
        for t in overdue:
            print(f"    OVERDUE: {t['title']} (due: {t['due_at']})")
        for t in soon:
            print(f"    SOON: {t['title']} (due: {t['due_at']})")
    except Exception as e:
        print(f"  Reminder check failed: {e}")

    # List tasks
    try:
        resp3 = opener.open(f"{BASE}/api/tasks", timeout=10)
        tasks = json.loads(resp3.read())
        print(f"  Total tasks: {len(tasks)}")
        for t in tasks:
            due = t.get("due_at", "none")
            remind = t.get("is_reminder", False)
            completed = t.get("completed", False)
            title = t.get("title", "?")
            print(f"    [{('X' if completed else ' ')}] {'🔔 ' if remind else '   '}{title} | due: {due}")
    except Exception as e:
        print(f"  Tasks fetch failed: {e}")
