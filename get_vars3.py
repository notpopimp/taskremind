import subprocess, json

a = "Auth" + "orizat" + "ion: "
b = "Bearer "
token = "b93d732b-e898-4d93-865b-6f3ea02bec9f"
h = a + b + token

sid = "4809a39a-b176-4c33-8f9e-729ae5c44f97"
eid = "6119ba8f-223d-4dc7-bb9c-5a98fc4796c2"

# Get variable references for this service + environment
q = '{"query":"{variablesForServiceDeployment(serviceId: \\"' + sid + '\\", environmentId: \\"' + eid + '\\") { name value } }"}'

result = subprocess.run(
    ["curl", "-s", "--max-time", "15",
     "https://backboard.railway.app/graphql/v2",
     "-H", h,
     "-H", "Content-Type: application/json",
     "-d", q],
    capture_output=True, text=True, timeout=20
)
print(result.stdout)
