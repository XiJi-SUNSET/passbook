"""序列化 + 原子写 + 备份轮转。

保存流程：
1. 生成随机 salt / 两个 IV / DEK
2. 主密码 →(Argon2id)→ KEK →(HKDF)→ header_key + data_key
3. 组装 header_plain(61B) → HMAC header_tag(16B)
4. data_key GCM 包装 DEK → wrapped_dek(48B)
5. DEK GCM 加密 gzip(payload) → payload
6. 备份轮转 → 先写 .tmp → fsync → 原子 rename

绝不 truncate 原文件后再写：一旦中途断电/崩溃，原文件仍完好。
"""

import gzip
import os
import shutil

from ..crypto.cipher import AesGcmCipher
from ..crypto.kdf import KdfParams, derive_key
from ..crypto.keys import (
    compute_header_tag,
    derive_data_key,
    derive_header_key,
    generate_dek,
    wrap_dek,
)
from .header import HEADER_LEN, Header

BACKUP_KEEP = 2  # 保留最近 2 份轮转备份
BACKUP_SUFFIXES = (".bak.1", ".bak.2")  # 越靠前越新
BROKEN_SUFFIX = ".broken"  # 恢复时给坏库留的现场，固定名覆盖（场景罕见）


def save(path: str, password: str, payload: bytes, params: KdfParams | None = None) -> Header:
    """把 payload（应为 JSON 字节）加密写入 path，返回实际使用的 Header。"""
    params = params or KdfParams()
    header = Header.new(params)
    header_plain = header.pack()
    assert len(header_plain) == HEADER_LEN

    kek = derive_key(password, params)
    header_key = derive_header_key(kek)
    data_key = derive_data_key(kek)

    header_tag = compute_header_tag(header_key, header_plain)

    dek = generate_dek()
    wrapped_dek = wrap_dek(data_key, dek, header.dek_iv, aad=header_plain)

    body = gzip.compress(payload)
    payload_ct = AesGcmCipher(dek).encrypt(
        header.payload_iv, body, aad=header_plain + wrapped_dek
    )

    blob = header_plain + header_tag + wrapped_dek + payload_ct

    _rotate_backup(path)
    atomic_write(path, blob)
    return header


def _rotate_backup(path: str) -> None:
    """保存前把旧文件向后轮转：path → .bak.1 → .bak.2（超出删除）。

    次序及其代价：轮转必须发生在新文件落盘之前——否则新文件一覆盖主路径，
    旧内容就没有来源可备份了。代价是若随后写盘失败，主路径会暂时没有库文件
    （内容仍在 .bak.1，可改名救回或走 recover），这个取舍是刻意选择的。
    """
    bak1 = f"{path}.bak.1"
    bak2 = f"{path}.bak.2"
    if os.path.exists(bak2):
        os.remove(bak2)
    if os.path.exists(bak1):
        os.replace(bak1, bak2)
    if os.path.exists(path):
        os.replace(path, bak1)


def restore_from(path: str, backup_path: str) -> None:
    """把备份的字节恢复回主库；当前主库先另存为 .broken 保留现场。

    只搬字节、不解密也不解析——备份是否完好由上层先验证再调用。
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"备份不存在：{backup_path}")
    with open(backup_path, "rb") as f:
        blob = f.read()
    if os.path.exists(path):
        shutil.copyfile(path, f"{path}{BROKEN_SUFFIX}")
    atomic_write(path, blob)


def atomic_write(path: str, data: bytes) -> None:
    """先写 .tmp 再 fsync 后 rename：任何时刻 path 要么是旧内容要么是完整新内容。

    - .tmp 名带 pid：同目录多进程并发保存时不会互踩。
    - POSIX 上额外 fsync 父目录：rename 的持久化依赖目录项落盘，只 fsync
      文件本身的话，断电后可能回退到旧文件（Windows 无此语义，跳过）。
    """
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(os.path.dirname(os.path.abspath(path)))


def _fsync_dir(path: str) -> None:
    """尽力 fsync 目录（仅 POSIX；不支持/失败都不影响主流程）。"""
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
