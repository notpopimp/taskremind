import subprocess, json

with open("C:/tmp/token.txt") as f:
    t = f.read().strip()

h = "Authorization: Bearer *** + t
pid = "f18f9f53-0aa1-49c4-95ce-0e734578e209"
Q = '{"query":"{environments(projectId:\\"' + pid + '\\"){id name}}"}'
r = subprocess.run(["curl","-s","--max-time","15","https://backboard.railway.app/graphql/v2","-H",h,"-H","Content-Type: application/json","-d",Q],capture_output=True,text=True,timeout=20)
print(r.stdout)
