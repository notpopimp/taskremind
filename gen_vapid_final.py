from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

k = ec.generate_private_key(ec.SECP256R1())

priv_num = k.private_numbers().private_value
priv_bytes = priv_num.to_bytes(32, 'big')
priv_b64 = base64.urlsafe_b64encode(priv_bytes).rstrip(b'=').decode()

pub = k.public_key()
pub_bytes = pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
pub_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode()

print("VAPID_PRIVATE_KEY=" + priv_b64)
print("VAPID_PUBLIC_KEY=" + pub_b64)
