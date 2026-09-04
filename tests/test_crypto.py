"""AES-GCM 加解密测试：往返、错误密钥/IV、篡改、AAD 不一致。"""

import os

import pytest
from cryptography.exceptions import InvalidTag

from passbook.crypto.cipher import AesGcmCipher

KEY = os.urandom(32)
IV = os.urandom(12)


def test_encrypt_decrypt_roundtrip():
    ct = AesGcmCipher(KEY).encrypt(IV, "hello 密码本".encode("utf-8"), b"aad")
    assert AesGcmCipher(KEY).decrypt(IV, ct, b"aad") == "hello 密码本".encode("utf-8")


def test_ciphertext_includes_16b_tag():
    ct = AesGcmCipher(KEY).encrypt(IV, b"x" * 10)
    assert len(ct) == 10 + 16


def test_wrong_key_fails():
    ct = AesGcmCipher(KEY).encrypt(IV, b"secret")
    with pytest.raises(InvalidTag):
        AesGcmCipher(os.urandom(32)).decrypt(IV, ct)


def test_wrong_iv_fails():
    ct = AesGcmCipher(KEY).encrypt(IV, b"secret")
    with pytest.raises(InvalidTag):
        AesGcmCipher(KEY).decrypt(os.urandom(12), ct)


def test_tampered_ciphertext_fails():
    ct = bytearray(AesGcmCipher(KEY).encrypt(IV, b"secret"))
    ct[5] ^= 0x01
    with pytest.raises(InvalidTag):
        AesGcmCipher(KEY).decrypt(IV, bytes(ct))


def test_aad_mismatch_fails():
    ct = AesGcmCipher(KEY).encrypt(IV, b"secret", b"right-aad")
    with pytest.raises(InvalidTag):
        AesGcmCipher(KEY).decrypt(IV, ct, b"wrong-aad")
