import base64

from cryptography.fernet import Fernet


def _get_fernet(key: str) -> Fernet:
    # Key must be 32 url-safe base64-encoded bytes; pad if short for dev convenience
    raw = key.encode()
    # Ensure proper base64 padding to 32 bytes
    padded = base64.urlsafe_b64encode(raw[:32].ljust(32, b"\x00"))
    return Fernet(padded)


def encrypt(plaintext: str, key: str) -> str:
    f = _get_fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: str) -> str:
    f = _get_fernet(key)
    return f.decrypt(ciphertext.encode()).decode()
