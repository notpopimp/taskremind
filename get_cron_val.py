import json, urllib.request
token = open(r'C:\tmp\token.txt').read().strip()
query = {"query": "{environment(id:\"6119ba8f-223d-4dc7-bb9c-5a98fc4796c2\"){variables{edges{node{id name value}}}}}"}
req = urllib.request.Request(
    "https://backboard.railway.app/graphql/v2",
    data=json.dumps(query).encode(),
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
for edge in data['data']['environment']['variables']['edges']:
    if edge['node']['name'] == 'CRON_SECRET':
        print(edge['node']['value'])
        break