import subprocess, base64, json

# Use cryptography to generate VAPID keys
script = """
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

key = ec.generate_private_key(ec.SECP256R1())
priv_raw = key.private_bytes(
    serialization.Encoding.Raw,
    serialization.PrivateFormat.Raw,
    serialization.NoEncryption()
)
pub_raw = key.public_key().public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw
)
p = base64.urlsafe_b64encode(priv_raw).rstrip(b'=').decode()
q = base64.urlsafe_b64encode(pub_raw).rstrip(b'=').decode()
print(p)
print(q)
"""

r = subprocess.run(["python", "-c", script], capture_output=True, text=True, timeout=10)
lines = r.stdout.strip().split("\n")
if len(lines) >= 2:
    print("VAPID_PRIVATE:", lines[0])
    print("VAPID_PUBLIC:", lines[1])
