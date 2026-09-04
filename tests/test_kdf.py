"""KDF 派生测试：确定性、盐/密码区分性、输出长度。"""

from passbook.crypto.kdf import KdfParams, derive_key

SALT = b"\x00" * 16


def test_derive_key_deterministic():
    p = KdfParams(memory_mib=1, iterations=1, parallelism=1, salt=SALT)
    assert derive_key("same-pass", p) == derive_key("same-pass", p)


def test_key_length_is_32():
    p = KdfParams(memory_mib=1, iterations=1, parallelism=1, salt=SALT)
    assert len(derive_key("abc", p)) == 32


def test_different_salt_gives_different_key():
    p1 = KdfParams(memory_mib=1, iterations=1, parallelism=1, salt=SALT)
    p2 = KdfParams(memory_mib=1, iterations=1, parallelism=1, salt=b"\xff" * 16)
    assert derive_key("abc", p1) != derive_key("abc", p2)


def test_different_password_gives_different_key():
    p = KdfParams(memory_mib=1, iterations=1, parallelism=1, salt=SALT)
    assert derive_key("pass-a", p) != derive_key("pass-b", p)


def test_invalid_params_rejected():
    import pytest

    with pytest.raises(ValueError):
        KdfParams(memory_mib=0)
    with pytest.raises(ValueError):
        KdfParams(iterations=0)
    with pytest.raises(ValueError):
        KdfParams(parallelism=0)
