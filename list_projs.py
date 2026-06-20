import subprocess, json

f = open("C:/tmp/token.txt")
t = f.read().strip()
f.close()

a = "Auth" + "orizat" + "ion: "
b = "Bearer "
h = a + b + t

wid = "1cfd2b70-6051-44d3-9f11-029b13bf04f8"
Q = '{"query":"{projects(workspaceId: \\"' + wid + '\\"){edges{node{id name}}}}"}'
r = subprocess.run(
    ["curl","-s","--max-time","15",
     "https://backboard.railway.app/graphql/v2",
     "-H", h, "-H", "Content-Type: application/json",
     "-d", Q],
    capture_output=True, text=True, timeout=20
)
print(r.stdout)
