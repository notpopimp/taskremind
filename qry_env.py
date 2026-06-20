import json, urllib.request
# Read token
with open(r"C:\tmp\token.txt") as f:
    token = f.read().strip()

pid = "f18f9f53-0aa1-49c4-95ce-0e734578e209"
env_id = "6119ba8f-223d-4dc7-bb9c-5a98fc4796c2"

query = {"query": f'{{environment(id:"{env_id}"){{variables{{edges{{node{{id name}}}}}}}}}}'}
req = urllib.request.Request(
    "https://backboard.railway.app/graphql/v2",
    data=json.dumps(query).encode(),
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
)
resp = urllib.request.urlopen(req)
print(resp.read().decode())
