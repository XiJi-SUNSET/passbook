"""双层密钥测试：DEK 包装往返、错误密钥、HKDF 用途分离、头认证。"""

import pytest
from cryptography.exceptions import InvalidTag

from passbook.crypto.keys import (
    compute_header_tag,
    derive_data_key,
    derive_header_key,
    generate_dek,
    unwrap_dek,
    wrap_dek,
)

KEK = b"\x11" * 32


def test_generate_dek_is_32_bytes_random():
    a, b = generate_dek(), generate_dek()
    assert len(a) == 32
    assert a != b


def test_header_and_data_keys_differ():
    assert derive_header_key(KEK) != derive_data_key(KEK)
    assert len(derive_header_key(KEK)) == 16
    assert len(derive_data_key(KEK)) == 32


def test_wrap_unwrap_roundtrip():
    dek = generate_dek()
    iv = b"\x22" * 12
    wrapped = wrap_dek(derive_data_key(KEK), dek, iv)
    assert len(wrapped) == 48
    assert unwrap_dek(derive_data_key(KEK), wrapped, iv) == dek


def test_unwrap_wrong_key_fails():
    dek = generate_dek()
    iv = b"\x22" * 12
    wrapped = wrap_dek(derive_data_key(KEK), dek, iv)
    with pytest.raises(InvalidTag):
        unwrap_dek(derive_data_key(KEK + b"\x00"), wrapped, iv)


def test_header_tag_detects_tamper():
    header_plain = b"H" * 61
    tag = compute_header_tag(derive_header_key(KEK), header_plain)
    assert tag != compute_header_tag(derive_header_key(KEK), header_plain[:-1] + b"X")
    assert len(tag) == 16
