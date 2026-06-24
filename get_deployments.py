import json, urllib.request
token = open(r'C:\tmp\token.txt').read().strip()
query = {"query": 'query { project(id:"f18f9f53-0aa1-49c4-95ce-0e734578e209") { id name deployments(last:5) { edges { node { id meta status createdAt } } } } }'}
req = urllib.request.Request(
    "https://backboard.railway.app/graphql/v2",
    data=json.dumps(query).encode(),
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print(json.dumps(data, indent=2))
