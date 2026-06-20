import urllib.request, json

BASE = "https://web-production-2b7e.up.railway.app"

for user in ["Ben", "Rachel", "Sam"]:
    # Login
    data = json.dumps({"username": user, "pin": "0000"}).encode()
    req = urllib.request.Request(f"{BASE}/api/login", data=data,
        headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        login = json.loads(resp.read())
        token = login.get("token", "")
        print(f"{user}: Login OK, token={token[:20]}...")
    except Exception as e:
        print(f"{user}: Login failed - {e}")
        continue

    # Check reminders
    req2 = urllib.request.Request(f"{BASE}/api/reminders",
        headers={"Authorization": f"Bearer {token}"})
    try:
        resp2 = urllib.request.urlopen(req2, timeout=10)
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
    req3 = urllib.request.Request(f"{BASE}/api/tasks",
        headers={"Authorization": f"Bearer {token}"})
    try:
        resp3 = urllib.request.urlopen(req3, timeout=10)
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
