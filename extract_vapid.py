import subprocess, base64, json

# Read the private key
with open("/tmp/vapid_private.pem") as f:
    priv_pem = f.read()

with open("/tmp/vapid_public.pem") as f:
    pub_pem = f.read()

# Extract raw key bytes using openssl
def get_raw_key(pem_path, is_private=True):
    r = subprocess.run(
        ["openssl", "ec", "-in", pem_path, "-noout", "-text"],
        capture_output=True, text=True
    )
    output = r.stdout
    # Parse hex bytes
    in_priv = False
    hex_chunks = []
    for line in output.split("\n"):
        if "priv:" in line.lower():
            in_priv = True
            continue
        if "pub:" in line.lower() or "ASN1" in line:
            in_priv = False
        if in_priv and ":" in line.replace(" ", ""):
            hex_str = line.strip().replace(":", "").replace(" ", "")
            if hex_str:
                hex_chunks.append(hex_str)
    if hex_chunks:
        raw = bytes.fromhex("".join(hex_chunks))
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

# Alternative: use py-vapid
r = subprocess.run(
    ["python", "-c", """
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import base64

with open('/tmp/vapid_private.pem', 'rb') as f:
    key = serialization.load_pem_private_key(f.read(), password=None)
    priv = key.private_numbers().private_value.to_bytes(32, 'big')
    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw
    )
    print('PRIV:' + base64.urlsafe_b64encode(priv).rstrip(b'=').decode())
    print('PUB:' + base64.urlsafe_b64encode(pub).rstrip(b'=').decode())
"""],
    capture_output=True, text=True, timeout=10
)
print(r.stdout)
if r.stderr:
    print("ERR:", r.stderr[:200])
