with open(r'C:\Users\cages\taskremind\sgkey.txt') as f:
    key = f.read().strip()

import urllib.request, json, ssl
ctx = ssl.create_default_context()

# Check sender identities
req = urllib.request.Request(
    'https://api.sendgrid.com/v3/senders',
    headers={'Authorization': 'Bearer ' + key})
try:
    resp = urllib.request.urlopen(req, context=ctx, timeout=15)
    data = json.loads(resp.read())
    for s in data:
        print(f"ID: {s.get('id')} From: {s.get('from',{}).get('email','?')} "
              f"Verified: {s.get('verified',{}).get('status')} "
              f"Nickname: {s.get('nickname','')}")
except Exception as e:
    print(f"Error: {e}")
