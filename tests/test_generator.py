"""强密码生成器测试：随机性、字符集保证、可读性、熵与强度分级。"""

import math

import pytest

from passbook.services.generator import (
    AMBIGUOUS,
    CHARS_DIGITS,
    CHARS_LOWER,
    CHARS_SYMBOLS,
    CHARS_UPPER,
    DEFAULT_LENGTH,
    entropy_bits,
    generate,
    password_strength,
)


def test_default_length():
    pw = generate()
    assert len(pw) == DEFAULT_LENGTH


def test_custom_length():
    for n in (8, 16, 32, 64):
        assert len(generate(length=n)) == n


def test_only_digits():
    pw = generate(length=10, lower=False, upper=False, symbols=False)
    assert set(pw) <= set(CHARS_DIGITS)
    assert len(pw) == 10


def test_only_symbols():
    pw = generate(length=12, lower=False, upper=False, digits=False)
    assert set(pw) <= set(CHARS_SYMBOLS)


def test_each_enabled_pool_at_least_min_each():
    pw = generate(length=12, min_each=2)
    counts = {
        "lower": sum(1 for c in pw if c in CHARS_LOWER),
        "upper": sum(1 for c in pw if c in CHARS_UPPER),
        "digit": sum(1 for c in pw if c in CHARS_DIGITS),
        "symbol": sum(1 for c in pw if c in CHARS_SYMBOLS),
    }
    assert all(v >= 2 for v in counts.values())


def test_has_symbols_by_default():
    pw = generate()
    assert any(c in CHARS_SYMBOLS for c in pw)


def test_exclude_ambiguous():
    for _ in range(200):
        pw = generate(length=20, exclude_ambiguous=True)
        assert not any(c in AMBIGUOUS for c in pw)


def test_randomness():
    seen = {generate() for _ in range(50)}
    assert len(seen) == 50  # CSPRNG 几乎不可能碰撞


def test_length_too_short_raises():
    with pytest.raises(ValueError):
        generate(length=3)  # 4 个集合各至少 1 个，3 不够


def test_no_pool_raises():
    with pytest.raises(ValueError):
        generate(lower=False, upper=False, digits=False, symbols=False)


def test_entropy_bits():
    # 6 位纯数字：6 × log2(10) ≈ 19.93
    assert entropy_bits("123456", alphabet=CHARS_DIGITS) == pytest.approx(
        6 * math.log2(10), rel=1e-9
    )
    assert entropy_bits("") == 0.0


def test_password_strength_weak():
    assert password_strength("abc123") == "weak"       # 短
    assert password_strength("123456789012") == "weak"  # 长度够但纯数字


def test_password_strength_ok():
    assert password_strength("abc1234567") == "ok"  # 10 位 + 2 类


def test_password_strength_strong():
    assert password_strength("Abc123!@#xYz0u8Qw") == "strong"  # 16 位 + 4 类
