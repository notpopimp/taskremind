from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

priv_raw = private_key.private_bytes(
    serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
)
pub_raw = public_key.public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw
)

print("VAPID_PRIVATE_KEY=" + b64url(priv_raw))
print("VAPID_PUBLIC_KEY=" + b64url(pub_raw))
