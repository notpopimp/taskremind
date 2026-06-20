import subprocess, json

with open(r'C:\tmp\token.txt') as f:
    token = f.read().strip()

query = json.dumps({"query": "query { project(id: \"f18f9f53-0aa1-49c4-95ce-0e734578e209\") { id name environments { edges { node { id name } } } } }"})

cmd = [
    "curl", "-s", "--max-time", "15",
    "https://backboard.railway.app/graphql/v2",
    "-H", "Authorization: Bearer " + token,
    "-H", "Content-Type: application/json",
    "-d", query
]
print("running query...", flush=True)
r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)

data = json.loads(r.stdout)
print(json.dumps(data, indent=2))
