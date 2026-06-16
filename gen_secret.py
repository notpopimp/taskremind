import secrets
val = secrets.token_hex(32)
with open("C:/tmp/cron_secret.txt", "w") as f:
    f.write(val)
print("ok")
