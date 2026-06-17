from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

k = ec.generate_private_key(ec.SECP256R1())
pr = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
pu = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
pb = base64.urlsafe_b64encode(pr).rstrip(b"=").decode()
ub = base64.urlsafe_b64encode(pu).rstrip(b"=").decode()
with open("C:/tmp/vk.txt","w") as f:
    f.write(pb + "\n" + ub)
