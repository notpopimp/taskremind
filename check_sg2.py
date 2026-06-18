import urllib.request, json, ssl, urllib.parse

with open(r'C:\Users\cages\AppData\Local\hermes\~\hermes\image_cache\sgkey.txt') as f:
    key = f.read().strip()

from_email = "waypoint.notifications@gmail.com"
to_email = "cagesliquidators@yahoo.com"

ctx = ssl.create_default_context()

# Check stats
stats_url = "https://api.sendgrid.com/v3/stats?start_date=2026-06-17&end_date=2026-06-17&aggregated_by=day"
req = urllib.request.Request(stats_url, headers={'Authorization': 'Bearer ' + key})
try:
    resp = urllib.request.urlopen(req, context=ctx, timeout=15)
    data = json.loads(resp.read())
    for stat in data:
        date = stat.get('date','?')
        for s in stat.get('stats',[]):
            m = s.get('metrics',{})
            print(f"Stats {date}: requests={m.get('requests',0)} delivered={m.get('delivered',0)} "
                  f"bounces={m.get('bounces',0)} blocks={m.get('blocks',0)}")
except Exception as e:
    print(f"Stats error: {e}")

# Check specific messages
query = f"to_email='{to_email}'"
msg_url = "https://api.sendgrid.com/v3/messages?limit=10&query=" + urllib.parse.quote(query)
req2 = urllib.request.Request(msg_url, headers={'Authorization': 'Bearer ' + key})
try:
    resp2 = urllib.request.urlopen(req2, context=ctx, timeout=15)
    data2 = json.loads(resp2.read())
    msgs = data2.get('messages', [])
    print(f"\nMessages to {to_email}: {len(msgs)}")
    for m in msgs[:3]:
        print(json.dumps(m, indent=2)[:600])
except Exception as e:
    print(f"Messages error: {e}")
