import json, urllib.request
token = open(r'C:\tmp\token.txt').read().strip()

# Try to find the VariableValue or EnvironmentVariable type
queries = [
    'query { __type(name: "Environment") { fields { name type { name kind } } } }',
    'query { __type(name: "Variable") { fields { name type { name kind } } } }',
    'query { __type(name: "EnvironmentVariables") { fields { name type { name kind } } } }',
    '{ __schema { types { name fields { name } } } }'
]

for q in queries:
    req = urllib.request.Request(
        "https://backboard.railway.app/graphql/v2",
        data=json.dumps({"query": q}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        print(f"Query: {q[:60]}...")
        print(json.dumps(data, indent=2))
        print("---")
    except Exception as e:
        print(f"Error for {q[:60]}: {e}")