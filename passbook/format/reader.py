"""反序列化 + 认证校验。

读取顺序决定安全边界：
1. 校验 magic/version → FormatError（不是本程序文件）
2. 解析明文头，用头的 KDF 参数派生 KEK
3. HMAC 校验 header_tag → 失败统一抛 CredentialsError
   （不区分密码错 vs 头被篡改，防解密预言机探测）
4. GCM 解包 DEK → 失败同样 CredentialsError
5. GCM 解密 payload → 失败抛 PayloadChecksumError（数据损坏，提示恢复备份）
"""

import gzip

from cryptography.exceptions import InvalidTag

from ..core.exceptions import CredentialsError, FormatError, PayloadChecksumError
from ..crypto.cipher import AesGcmCipher
from ..crypto.kdf import derive_key
from ..crypto.keys import (
    compute_header_tag,
    derive_data_key,
    derive_header_key,
    unwrap_dek,
)
from .header import HEADER_LEN, Header

HEADER_TAG_LEN = 16
WRAPPED_DEK_LEN = 48


def load(path: str, password: str) -> bytes:
    """读取并解密密码本，返回解压后的 payload 字节。"""
    with open(path, "rb") as f:
        blob = f.read()

    header = Header.unpack(blob)
    header_plain = blob[:HEADER_LEN]

    # 先约束 KDF 参数再派生密钥：文件头此刻还没通过 HMAC 认证，
    # 恶意 .pbk 塞入天量 memory/iterations 会在这里就把内存打爆。
    # 超限当作"文件损坏/伪造"处理，而非密码错误。
    try:
        params = header.to_kdf_params()
    except ValueError:
        raise FormatError("KDF 参数异常（文件损坏或伪造）") from None

    kek = derive_key(password, params)
    header_key = derive_header_key(kek)
    data_key = derive_data_key(kek)

    # 1. 头认证
    expected = compute_header_tag(header_key, header_plain)
    actual = blob[HEADER_LEN:HEADER_LEN + HEADER_TAG_LEN]
    if len(actual) != HEADER_TAG_LEN or not _const_time_eq(expected, actual):
        raise CredentialsError("主密码错误或文件已被篡改")

    # 2. 解包 DEK
    wrapped = blob[HEADER_LEN + HEADER_TAG_LEN:HEADER_LEN + HEADER_TAG_LEN + WRAPPED_DEK_LEN]
    try:
        dek = unwrap_dek(data_key, wrapped, header.dek_iv, aad=header_plain)
    except InvalidTag:
        raise CredentialsError("主密码错误或文件已被篡改") from None

    # 3. 解密 payload
    payload_ct = blob[HEADER_LEN + HEADER_TAG_LEN + WRAPPED_DEK_LEN:]
    try:
        body = AesGcmCipher(dek).decrypt(
            header.payload_iv, payload_ct, aad=header_plain + wrapped
        )
    except InvalidTag:
        raise PayloadChecksumError("数据完整性校验失败，请从备份恢复") from None

    try:
        return gzip.decompress(body)
    except (OSError, EOFError):
        raise FormatError("数据块损坏（gzip 解压失败）") from None


def inspect(path: str) -> Header:
    """只读文件头（不验证密码），供 UI 展示 KDF 参数、版本等元信息。"""
    with open(path, "rb") as f:
        blob = f.read()
    return Header.unpack(blob)


def _const_time_eq(a: bytes, b: bytes) -> bool:
    import hmac

    return hmac.compare_digest(a, b)
