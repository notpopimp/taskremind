#!/bin/bash
# Upload remaining files to GitHub
TOKEN=*** /tmp/real_token.txt)

if [ ${#TOKEN} -ne 40 ]; then
  echo "Bad token length: ${#TOKEN}"
  exit 1
fi

API="https://api.github.com/repos/notpopimp/taskremind/contents"

# Upload static files
curl -s -X PUT -H "Authorization: token $TOKEN" -H "Content-Type: application/json" \
  -d @- "$API/static/manifest.json" <<'ENDJSON1'
{"message":"Add manifest.json","content":"ewogICAgIm5hbWUiOiAiVGFza1JlbWluZCIsCiAgICAic2hvcnRfbmFtZSI6ICJUYXNrUmVtaW5kIiwKICAgICJkZXNjcmlwdGlvbiI6ICJTaW1wbGUgdGFzayByZW1pbmRlciBhcHAgd2l0aCBzaGFyZWFibGUgbGlua3MiLAogICAgInN0YXJ0X3VybCI6ICIvIiwKICAgICJkaXNwbGF5IjogInN0YW5kYWxvbmUiLAogICAgImJhY2tncm91bmRfY29sb3IiOiAiIzBmMGYyMyIsCiAgICAidGhlbWVfY29sb3IiOiAiIzFhMWEyZSIsCiAgICAiaWNvbnMiOiBbCiAgICAgICAgewogICAgICAgICAgICAic3JjIjogImRhdGE6aW1hZ2Uvc3ZnK3htbCw8c3ZnIHhtbG5zPSdodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2Zycgdmlld0JveD0nMCAwIDEwMCAxMDAnPjxjaXJjbGUgY3g9JzUwJyBjeT0nNTAnIHI9JzQ1JyBmaWxsPSclMjMxYTFhMmUnIHN0cm9rZT0nJTIzNGZjM2Y3JyBzdHJva2Utd2lkdGg9JzQnLz48Y2lyY2xlIGN4PSc1MCcgY3k9JzMwJyByPScyJyBmaWxsPSclMjM0ZmMzZjcnLz48bGluZSB4MT0nNTAnIHkxPSc1MCcgeDI9JzUwJyB5Mj0nMjUnIHN0cm9rZT0nJTIzNGZjM2Y3JyBzdHJva2Utd2lkdGg9JzMnIHN0cm9rZS1saW5lY2FwPSdyb3VuZCcvPjxsaW5lIHgxPSc1MCcgeTE9JzUwJyB4Mj0nNzAnIHkyPSc1MCcgc3Ryb2tlPSclMjM0ZmMzZjcnIHN0cm9rZS13aWR0aD0nMycgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJy8+PC9zdmc+IiwKICAgICAgICAgICAgInNpemVzIjogImFueSIsCiAgICAgICAgICAgICJ0eXBlIjogImltYWdlL3N2Zyt4bWwiCiAgICAgICAgfQogICAgXQp9Cg==","branch":"master"}
ENDJSON1

echo "manifest.json done"