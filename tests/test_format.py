"""文件格式端到端测试：往返、错误密码、篡改、原子写、备份轮转。"""

import os

import pytest

from passbook.core.exceptions import CredentialsError, FormatError, PayloadChecksumError
from passbook.format.reader import inspect, load
from passbook.format.writer import save
from tests.conftest import PASSWORD, PAYLOAD


def _save(vault_path, fast_params, payload=PAYLOAD, password=PASSWORD):
    return save(vault_path, password, payload.encode("utf-8"), params=fast_params)


def test_save_load_roundtrip(vault_path, fast_params):
    _save(vault_path, fast_params)
    assert load(vault_path, PASSWORD).decode("utf-8") == PAYLOAD


def test_unicode_payload_roundtrip(vault_path, fast_params):
    payload = '{"title": "密码本·测试", "note": "包含 emoji 🎉 与中文"}'
    _save(vault_path, fast_params, payload=payload)
    assert load(vault_path, PASSWORD).decode("utf-8") == payload


def test_wrong_password_raises_credentials(vault_path, fast_params):
    _save(vault_path, fast_params)
    with pytest.raises(CredentialsError):
        load(vault_path, "wrong-password")


def test_tampered_header_raises_credentials(vault_path, fast_params):
    _save(vault_path, fast_params)
    blob = bytearray(open(vault_path, "rb").read())
    blob[20] ^= 0x01  # 改 salt 一个字节 → HMAC 校验失败
    open(vault_path, "wb").write(bytes(blob))
    with pytest.raises(CredentialsError):
        load(vault_path, PASSWORD)


def test_tampered_payload_raises_checksum(vault_path, fast_params):
    _save(vault_path, fast_params)
    blob = bytearray(open(vault_path, "rb").read())
    blob[-1] ^= 0x01  # 改 payload 末尾一个字节 → GCM 认证失败
    open(vault_path, "wb").write(bytes(blob))
    with pytest.raises(PayloadChecksumError):
        load(vault_path, PASSWORD)


def test_not_passbook_file_raises_format(vault_path, fast_params):
    open(vault_path, "wb").write(b"this is not a passbook file at all")
    with pytest.raises(FormatError):
        load(vault_path, PASSWORD)


def test_unsupported_version_raises_format(vault_path, fast_params):
    _save(vault_path, fast_params)
    blob = bytearray(open(vault_path, "rb").read())
    blob[8:10] = (999).to_bytes(2, "big")  # 伪造版本号
    open(vault_path, "wb").write(bytes(blob))
    with pytest.raises(FormatError):
        load(vault_path, PASSWORD)


def test_oversized_kdf_params_rejected_before_kdf(vault_path, fast_params):
    """恶意 .pbk 塞入天量 memory_mib：必须在派生密钥前拦下，不能把内存打爆。"""
    _save(vault_path, fast_params)
    blob = bytearray(open(vault_path, "rb").read())
    blob[11:15] = (100000).to_bytes(4, "big")  # 偏移 11：memory_mib (u32)
    open(vault_path, "wb").write(bytes(blob))
    with pytest.raises(FormatError):
        load(vault_path, PASSWORD)


def test_oversized_iterations_rejected(vault_path, fast_params):
    _save(vault_path, fast_params)
    blob = bytearray(open(vault_path, "rb").read())
    blob[15:19] = (99999).to_bytes(4, "big")  # 偏移 15：iterations (u32)
    open(vault_path, "wb").write(bytes(blob))
    with pytest.raises(FormatError):
        load(vault_path, PASSWORD)


def test_no_tmp_leftover_after_save(vault_path, fast_params):
    _save(vault_path, fast_params)
    assert not os.path.exists(f"{vault_path}.tmp")


def test_backup_rotation_keeps_two(vault_path, fast_params):
    _save(vault_path, fast_params)
    save(vault_path, PASSWORD, "second".encode(), params=fast_params)
    save(vault_path, PASSWORD, "third".encode(), params=fast_params)
    assert os.path.exists(f"{vault_path}.bak.1")
    assert os.path.exists(f"{vault_path}.bak.2")
    # 主库是最新内容
    assert load(vault_path, PASSWORD).decode() == "third"
    # bak.1 是上一次（second），bak.2 是最早一次（初始 payload）
    assert load(f"{vault_path}.bak.1", PASSWORD).decode() == "second"
    assert load(f"{vault_path}.bak.2", PASSWORD).decode() == PAYLOAD


def test_save_with_custom_password_rotates(vault_path, fast_params):
    save(vault_path, "master-one", "data-a".encode(), params=fast_params)
    save(vault_path, "master-two", "data-b".encode(), params=fast_params)
    assert load(vault_path, "master-two").decode() == "data-b"
    assert load(f"{vault_path}.bak.1", "master-one").decode() == "data-a"


def test_inspect_returns_header_meta(vault_path, fast_params):
    _save(vault_path, fast_params)
    h = inspect(vault_path)
    assert h.memory_mib == 1
    assert h.iterations == 1
    assert h.parallelism == 1
    assert len(h.salt) == 16
