import subprocess, json

token = "b93d732b-e898-4d93-865b-6f3ea02bec9f"

result = subprocess.run(
    ["curl", "-s", "--max-time", "15",
     "https://backboard.railway.app/graphql/v2",
     "-H", "Authorization: Bearer " + token,
     "-H", "Content-Type: application/json",
     "-d", '{"query":"{ __type(name: \\"Variable\\") { fields { name description } } }"}"],
    capture_output=True, text=True, timeout=20
)
print(result.stdout)
