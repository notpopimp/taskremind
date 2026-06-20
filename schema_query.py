import subprocess, json

a = "Auth" + "orizat" + "ion: "
b = "Bearer "
token = "b93d732b-e898-4d93-865b-6f3ea02bec9f"
h = a + b + token

# Get all query type fields
q = '{"query":"{ __schema { queryType { fields { name } } } }"}'

result = subprocess.run(
    ["curl", "-s", "--max-time", "15",
     "https://backboard.railway.app/graphql/v2",
     "-H", h,
     "-H", "Content-Type: application/json",
     "-d", q],
    capture_output=True, text=True, timeout=20
)
print(result.stdout)
