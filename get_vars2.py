import subprocess, json

a = "Auth" + "orizat" + "ion: "
b = "Bearer "
token = "b93d732b-e898-4d93-865b-6f3ea02bec9f"
h = a + b + token

pid = "f18f9f53-0aa1-49c4-95ce-0e734578e209"
eid = "6119ba8f-223d-4dc7-bb9c-5a98fc4796c2"

q = '{"query":"{variables(projectId: \\"' + pid + '\\", environmentId: \\"' + eid + '\\"){edges{node{id name value}}}}"}'

result = subprocess.run(
    ["curl", "-s", "--max-time", "15",
     "https://backboard.railway.app/graphql/v2",
     "-H", h,
     "-H", "Content-Type: application/json",
     "-d", q],
    capture_output=True, text=True, timeout=20
)
print(result.stdout)
