"""Password-based encryption (Fernet / PBKDF2)."""
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend


class SecureEncryption:
    """Simple encryption for password protection."""

    def __init__(self):
        pass

    def _derive_key(self, password, salt):
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return Fernet(key)

    def encrypt_data(self, text, password):
        salt = os.urandom(16)
        fernet = self._derive_key(password, salt)
        encrypted = fernet.encrypt(text.encode())
        return salt + encrypted

    def decrypt_data(self, encrypted_data, password):
        salt = encrypted_data[:16]
        encrypted = encrypted_data[16:]
        fernet = self._derive_key(password, salt)
        decrypted = fernet.decrypt(encrypted)
        return decrypted.decode()

    def encrypt_bytes(self, data_bytes, password):
        salt = os.urandom(16)
        fernet = self._derive_key(password, salt)
        encrypted = fernet.encrypt(data_bytes)
        return salt + encrypted

    def decrypt_bytes(self, encrypted_data, password):
        salt = encrypted_data[:16]
        encrypted = encrypted_data[16:]
        fernet = self._derive_key(password, salt)
        return fernet.decrypt(encrypted)
