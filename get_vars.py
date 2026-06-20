import subprocess, json

with open("C:/tmp/token.txt") as f:
    token = f.read().strip()

env_id = "6119ba8f-223d-4dc7-bb9c-5a98fc4796c2"

query = {
    "query": f'{{environment(id:"{env_id}"){{variables{{edges{{node{{id name value}}}}}}}}}}'
}

result = subprocess.run(
    ["curl", "-s", "--max-time", "15",
     "https://backboard.railway.app/graphql/v2",
     "-H", "Authorization: Bearer " + token,
     "-H", "Content-Type: application/json",
     "-d", json.dumps(query)],
    capture_output=True, text=True, timeout=20
)
print("STDOUT:", result.stdout[:2000])
print("STDERR:", result.stderr[:500])
if result.stdout:
    try:
        data = json.loads(result.stdout)
        env_data = data.get("data", {}).get("environment", {})
        if env_data:
            for edge in env_data.get("variables", {}).get("edges", []):
                node = edge["node"]
                print(f"  {node['name']}={node.get('value','?')[:60]}")
        else:
            print("Errors:", data.get("errors", "no data"))
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
