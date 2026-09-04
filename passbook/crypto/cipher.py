"""AES-256-GCM 封装（AEAD，自带完整性认证）。"""

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


class AesGcmCipher:
    """固定密钥的 GCM 加解密。密文格式 = 明文密文 + 16B 认证 tag。"""

    def __init__(self, key: bytes) -> None:
        if len(key) not in (16, 24, 32):
            raise ValueError(f"AES 密钥长度须为 16/24/32 字节，实际 {len(key)}")
        self._impl = AESGCM(key)

    def encrypt(self, iv: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
        return self._impl.encrypt(iv, plaintext, aad)

    def decrypt(self, iv: bytes, data: bytes, aad: bytes = b"") -> bytes:
        return self._impl.decrypt(iv, data, aad)

    @staticmethod
    def is_tag_error(exc: Exception) -> bool:
        return isinstance(exc, InvalidTag)
