"""明文文件头结构。

布局（大端，共 61 字节，不含 header_tag）：

    偏移   大小   字段
    0      8     magic = b"PASSBOOK"
    8      2     format_version (u16) = 1
    10     1     kdf_alg (u8) = 1 (Argon2id)
    11     4     memory_mib (u32)
    15     4     iterations (u32)
    19     1     parallelism (u8)
    20     16    salt
    36     1     cipher_alg (u8) = 1 (AES-256-GCM)
    37     12    dek_iv
    49     12    payload_iv

头之后依次为：header_tag(16B) | wrapped_dek(48B) | payload(变长)。

KDF 参数明文入头是刻意为之：不存参数，换机器/升级参数后旧库就打不开。
整个头（61B）被 header_key 的 HMAC 认证，防降级篡改。
"""

import secrets
import struct
from dataclasses import dataclass

from ..core.exceptions import FormatError
from ..crypto.kdf import KDF_ALG_ARGON2ID, KdfParams

MAGIC = b"PASSBOOK"
FORMAT_VERSION = 1
CIPHER_ALG_AES_GCM = 1
HEADER_LEN = 61
IV_LEN = 12

_STRUCT = ">8sHBIIB16sB12s12s"


@dataclass(frozen=True)
class Header:
    kdf_alg: int
    memory_mib: int
    iterations: int
    parallelism: int
    salt: bytes
    cipher_alg: int
    dek_iv: bytes
    payload_iv: bytes

    @classmethod
    def new(cls, params: KdfParams) -> "Header":
        return cls(
            kdf_alg=KDF_ALG_ARGON2ID,
            memory_mib=params.memory_mib,
            iterations=params.iterations,
            parallelism=params.parallelism,
            salt=params.salt,
            cipher_alg=CIPHER_ALG_AES_GCM,
            dek_iv=secrets.token_bytes(IV_LEN),
            payload_iv=secrets.token_bytes(IV_LEN),
        )

    def pack(self) -> bytes:
        return struct.pack(
            _STRUCT,
            MAGIC,
            FORMAT_VERSION,
            self.kdf_alg,
            self.memory_mib,
            self.iterations,
            self.parallelism,
            self.salt,
            self.cipher_alg,
            self.dek_iv,
            self.payload_iv,
        )

    @classmethod
    def unpack(cls, data: bytes) -> "Header":
        if len(data) < HEADER_LEN:
            raise FormatError("文件头不完整")
        (magic, version, kdf_alg, memory_mib, iterations, parallelism,
         salt, cipher_alg, dek_iv, payload_iv) = struct.unpack(_STRUCT, data[:HEADER_LEN])
        if magic != MAGIC:
            raise FormatError("不是密码本文件（magic 不匹配）")
        if version != FORMAT_VERSION:
            raise FormatError(f"不支持的格式版本：{version}")
        if kdf_alg != KDF_ALG_ARGON2ID:
            raise FormatError(f"不支持的 KDF 算法：{kdf_alg}")
        if cipher_alg != CIPHER_ALG_AES_GCM:
            raise FormatError(f"不支持的加密算法：{cipher_alg}")
        return cls(
            kdf_alg=kdf_alg,
            memory_mib=memory_mib,
            iterations=iterations,
            parallelism=parallelism,
            salt=salt,
            cipher_alg=cipher_alg,
            dek_iv=dek_iv,
            payload_iv=payload_iv,
        )

    def to_kdf_params(self) -> KdfParams:
        return KdfParams(
            memory_mib=self.memory_mib,
            iterations=self.iterations,
            parallelism=self.parallelism,
            salt=self.salt,
        )
