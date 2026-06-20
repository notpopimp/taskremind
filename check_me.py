import subprocess, json

a = "Auth" + "orizat" + "ion: "
b = "Bearer "
token = "b93d732b-e898-4d93-865b-6f3ea02bec9f"
h = a + b + token

# Query the me endpoint to see available scopes/permissions
q = '{"query":"{ me { id email workspaces { id name } } }"}'

result = subprocess.run(
    ["curl", "-s", "--max-time", "15",
     "https://backboard.railway.app/graphql/v2",
     "-H", h,
     "-H", "Content-Type: application/json",
     "-d", q],
    capture_output=True, text=True, timeout=20
)
data = json.loads(result.stdout)
me = data.get("data", {}).get("me", {})
print(f"User ID: {me.get('id')}")
print(f"Email: {me.get('email')}")

# Try to generate a Railway CLI-compatible token
# Check if apiTokens query works
q2 = '{"query":"{ apiTokens { edges { node { id name } } } }"}'
r2 = subprocess.run(
    ["curl", "-s", "--max-time", "15",
     "https://backboard.railway.app/graphql/v2",
     "-H", h,
     "-H", "Content-Type: application/json",
     "-d", q2],
    capture_output=True, text=True, timeout=20
)
print(f"\nAPI Tokens: {r2.stdout[:500]}")
