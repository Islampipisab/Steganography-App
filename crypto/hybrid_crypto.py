"""Hybrid cryptography: AES for data, RSA for AES key."""
import os
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding
from cryptography.hazmat.primitives import serialization

from config.settings import DEFAULT_PRIVATE_KEY_PATH, DEFAULT_PUBLIC_KEY_PATH


class HybridCrypto:
    """Hybrid cryptography: AES for data, RSA for AES key."""

    def __init__(self, rsa_public_key=None, rsa_private_key=None):
        if rsa_public_key is None or rsa_private_key is None:
            self.private_key, self.public_key = self._generate_rsa_keys()
        else:
            self.private_key = rsa_private_key
            self.public_key = rsa_public_key

    @staticmethod
    def _generate_rsa_keys(key_size=2048):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend(),
        )
        public_key = private_key.public_key()
        return private_key, public_key

    def generate_aes_key(self, key_size=256):
        return os.urandom(key_size // 8)

    def encrypt_aes_key(self, aes_key):
        return self.public_key.encrypt(
            aes_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

    def decrypt_aes_key(self, encrypted_aes_key):
        return self.private_key.decrypt(
            encrypted_aes_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

    def encrypt_data(self, data, aes_key, iv=None):
        if isinstance(data, str):
            data = data.encode("utf-8")
        if iv is None:
            iv = os.urandom(16)
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data) + padder.finalize()
        cipher = Cipher(
            algorithms.AES(aes_key),
            modes.CBC(iv),
            backend=default_backend(),
        )
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
        return encrypted_data, iv

    def decrypt_data(self, encrypted_data, aes_key, iv):
        cipher = Cipher(
            algorithms.AES(aes_key),
            modes.CBC(iv),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(encrypted_data) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        data = unpadder.update(padded_data) + unpadder.finalize()
        return data

    def encrypt_hybrid(self, data):
        aes_key = self.generate_aes_key(256)
        encrypted_data, iv = self.encrypt_data(data, aes_key)
        encrypted_key = self.encrypt_aes_key(aes_key)
        return {
            "encrypted_data": base64.b64encode(encrypted_data).decode("utf-8"),
            "encrypted_key": base64.b64encode(encrypted_key).decode("utf-8"),
            "iv": base64.b64encode(iv).decode("utf-8"),
        }

    def decrypt_hybrid(self, encrypted_package):
        encrypted_data = base64.b64decode(encrypted_package["encrypted_data"])
        encrypted_key = base64.b64decode(encrypted_package["encrypted_key"])
        iv = base64.b64decode(encrypted_package["iv"])
        aes_key = self.decrypt_aes_key(encrypted_key)
        return self.decrypt_data(encrypted_data, aes_key, iv)

    def save_rsa_keys(
        self,
        private_key_path=None,
        public_key_path=None,
    ):
        private_key_path = private_key_path or DEFAULT_PRIVATE_KEY_PATH
        public_key_path = public_key_path or DEFAULT_PUBLIC_KEY_PATH
        with open(private_key_path, "wb") as f:
            f.write(
                self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        with open(public_key_path, "wb") as f:
            f.write(
                self.public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )

    @staticmethod
    def load_rsa_keys(
        private_key_path=None,
        public_key_path=None,
    ):
        private_key_path = private_key_path or DEFAULT_PRIVATE_KEY_PATH
        public_key_path = public_key_path or DEFAULT_PUBLIC_KEY_PATH
        with open(private_key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(),
                password=None,
                backend=default_backend(),
            )
        with open(public_key_path, "rb") as f:
            public_key = serialization.load_pem_public_key(
                f.read(),
                backend=default_backend(),
            )
        return private_key, public_key

    def get_public_key_pem(self):
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    def get_private_key_pem(self):
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
