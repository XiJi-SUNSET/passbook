"""双层密钥管理。

主密码 →(Argon2id)→ KEK →(HKDF 扩展)→ 两个独立用途密钥：
- header_key(16B)：HMAC 认证文件头（无需解密即可验证文件是否被篡改）
- data_key (32B)：GCM 包装随机数据密钥 DEK

DEK(32B) 才是真正加密条目数据的密钥。改主密码 = 重新派生 KEK
再重包一次 DEK，库内容完全不用重加密。
"""

import hmac
import hashlib
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .cipher import AesGcmCipher

HEADER_TAG_LEN = 16
WRAPPED_DEK_LEN = 48  # 32B 密文 + 16B tag


def _hkdf(kek: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(kek)


def derive_header_key(kek: bytes) -> bytes:
    return _hkdf(kek, b"passbook:header", 16)


def derive_data_key(kek: bytes) -> bytes:
    return _hkdf(kek, b"passbook:data", 32)


def generate_dek() -> bytes:
    """生成随机 32 字节数据密钥（CSPRNG）。"""
    return secrets.token_bytes(32)


def compute_header_tag(header_key: bytes, header_plain: bytes) -> bytes:
    """对明文头做 HMAC-SHA256，取前 16 字节。"""
    return hmac.new(header_key, header_plain, hashlib.sha256).digest()[:HEADER_TAG_LEN]


def wrap_dek(data_key: bytes, dek: bytes, iv: bytes, aad: bytes = b"") -> bytes:
    """用 data_key 的 GCM 包装 DEK，返回 48 字节。"""
    return AesGcmCipher(data_key).encrypt(iv, dek, aad)


def unwrap_dek(data_key: bytes, wrapped: bytes, iv: bytes, aad: bytes = b"") -> bytes:
    """解包 DEK；data_key 不对会抛 InvalidTag，由调用方转成 CredentialsError。"""
    return AesGcmCipher(data_key).decrypt(iv, wrapped, aad)
