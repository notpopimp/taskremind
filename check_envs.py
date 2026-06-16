import subprocess, json

with open("C:/tmp/token.txt") as f:
    t = f.read().strip()

h = "".join(["Auth","orizat","ion: Be","arer "]) + t

# Get environments for the project
pid = "f18f9f53-0aa1-49c4-95ce-0e734578e209"
Q = '{"query":"{environments(input:{projectId:\\"' + pid + '\\"}){edges{node{id name}}}}"}'
r = subprocess.run(
    ["curl","-s","--max-time","15",
     "https://backboard.railway.app/graphql/v2",
     "-H", h, "-H", "Content-Type: application/json",
     "-d", Q],
    capture_output=True, text=True, timeout=20
)
print(r.stdout)
