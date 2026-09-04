"""密钥派生：Argon2id 从主密码派生 KEK。

参数（memory/iterations/parallelism/salt）必须明文存入文件头，
否则换机器、升级参数后旧库永远打不开。
"""

import secrets
from dataclasses import dataclass, field

import argon2.low_level as al

KDF_ALG_ARGON2ID = 1
DEFAULT_MEMORY_MIB = 64
DEFAULT_ITERATIONS = 3
DEFAULT_PARALLELISM = 2
# 上限：挡住恶意 .pbk 文件在"文件头还没通过 HMAC 认证"之前，用天量 KDF 参数
# 触发内存耗尽 / CPU 打满（DoS）。正常用户绝不会触顶，宽松到不影响合法使用。
MAX_MEMORY_MIB = 1024
MAX_ITERATIONS = 100
MAX_PARALLELISM = 32
SALT_LEN = 16
KEY_LEN = 32


@dataclass(frozen=True)
class KdfParams:
    """Argon2id 参数集。生产默认 64MiB / t=3 / p=2；测试请降低以加速。"""

    memory_mib: int = DEFAULT_MEMORY_MIB
    iterations: int = DEFAULT_ITERATIONS
    parallelism: int = DEFAULT_PARALLELISM
    salt: bytes = field(default_factory=lambda: secrets.token_bytes(SALT_LEN))

    def __post_init__(self) -> None:
        if not (1 <= self.memory_mib <= MAX_MEMORY_MIB):
            raise ValueError(f"memory_mib 须在 1~{MAX_MEMORY_MIB} 之间")
        if not (1 <= self.iterations <= MAX_ITERATIONS):
            raise ValueError(f"iterations 须在 1~{MAX_ITERATIONS} 之间")
        if not (1 <= self.parallelism <= MAX_PARALLELISM):
            raise ValueError(f"parallelism 须在 1~{MAX_PARALLELISM} 之间")


def derive_key(password: str, params: KdfParams) -> bytes:
    """由主密码派生 32 字节 KEK。"""
    return al.hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=params.salt,
        time_cost=params.iterations,
        memory_cost=params.memory_mib * 1024,  # argon2 单位是 KiB
        parallelism=params.parallelism,
        hash_len=KEY_LEN,
        type=al.Type.ID,
    )
