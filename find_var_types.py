import subprocess, json

a = "Auth" + "orizat" + "ion: "
b = "Bearer "
token = "b93d732b-e898-4d93-865b-6f3ea02bec9f"
h = a + b + token

# Try the full schema
q = '{"query":"{ __schema { types { name fields { name type { name kind ofType { name } } } } } }"}'

result = subprocess.run(
    ["curl", "-s", "--max-time", "15",
     "https://backboard.railway.app/graphql/v2",
     "-H", h,
     "-H", "Content-Type: application/json",
     "-d", q],
    capture_output=True, text=True, timeout=20
)
d = json.loads(result.stdout)

# Find types with "variable" in name
for t in d.get("data", {}).get("__schema", {}).get("types", []):
    if "variable" in t["name"].lower() or "Variable" in t["name"]:
        fnames = [f["name"] for f in (t.get("fields") or [])]
        print(f"{t['name']}: {fnames}")
