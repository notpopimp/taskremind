import subprocess, base64, json, sys, os

# Generate VAPID keys using subprocess to call openssl directly
result = subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-outform", "DER"],
                       capture_output=True, timeout=10)

if result.returncode != 0:
    print("ERROR: openssl failed")
    sys.exit(1)

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

private_key = serialization.load_der_private_key(result.stdout, password=None)
priv_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')
pub_key = private_key.public_key()
pub_bytes = pub_key.public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw
)

private_b64 = base64.urlsafe_b64encode(priv_bytes).rstrip(b'=').decode()
public_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode()

# Write to files
with open("C:/tmp/vapid_private.key", "w") as f:
    f.write(private_b64)
with open("C:/tmp/vapid_public.key", "w") as f:
    f.write(public_b64)

print("VAPID_PUBLIC_KEY=" + public_b64)
