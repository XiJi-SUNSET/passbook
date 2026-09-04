"""强密码生成器与主密码强度评估。

安全要求：
- 全部随机性来自 secrets（CSPRNG），绝不用 random。
- 默认保证启用的字符集每类至少出现一个，避免生成出"全小写"这种弱密码。
- 熵估算与强度分级用于 P5 拒绝弱主密码。
"""

import math
import secrets

CHARS_LOWER = "abcdefghijklmnopqrstuvwxyz"
CHARS_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHARS_DIGITS = "0123456789"
# 排除在 shell / CSV / URL 里容易惹麻烦的字符：引号、反斜杠、空格
CHARS_SYMBOLS = "!@#$%^&*()-_=+[]{};:,.<>?/~"

AMBIGUOUS = "0O1lI|"  # 易混淆字符（可读性选项）

DEFAULT_LENGTH = 20


def generate(
    length: int = DEFAULT_LENGTH,
    lower: bool = True,
    upper: bool = True,
    digits: bool = True,
    symbols: bool = True,
    min_each: int = 1,
    exclude_ambiguous: bool = False,
) -> str:
    """生成随机强密码。

    参数：
        length: 密码长度，必须 >= 启用的字符集数 × min_each
        lower/upper/digits/symbols: 各字符集开关
        min_each: 每个启用字符集保证出现的最小字符数
        exclude_ambiguous: 排除易混淆字符（0O1lI|）
    """
    pools = []
    if lower:
        pools.append(CHARS_LOWER)
    if upper:
        pools.append(CHARS_UPPER)
    if digits:
        pools.append(CHARS_DIGITS)
    if symbols:
        pools.append(CHARS_SYMBOLS)
    if not pools:
        raise ValueError("至少启用一个字符集")

    if exclude_ambiguous:
        pools = ["".join(c for c in p if c not in AMBIGUOUS) for p in pools]
        pools = [p for p in pools if p]  # 排除后集合可能被清空

    if length < len(pools) * min_each:
        raise ValueError(
            f"长度 {length} 不足以容纳 {len(pools)} 个字符集各 {min_each} 个字符"
        )

    # 先抽"每个集合至少 min_each 个"，再从全集抽剩余，最后 CSPRNG 洗牌
    chars = [secrets.choice(p) for p in pools for _ in range(min_each)]
    full = "".join(pools)
    chars += [secrets.choice(full) for _ in range(length - len(chars))]
    _shuffle(chars)
    return "".join(chars)


def _shuffle(items: list) -> None:
    """Fisher–Yates 洗牌，用 secrets.randbelow 保证随机源安全。"""
    for i in range(len(items) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        items[i], items[j] = items[j], items[i]


def entropy_bits(password: str, alphabet: str | None = None) -> float:
    """估算密码熵（bit）：长度 × log2(字符表大小)。

    alphabet 不传时按密码实际出现的字符估算，适合评估随机生成的密码；
    对人工设定的主密码此值偏乐观（人不是均匀随机），仅作展示用。
    """
    if not password:
        return 0.0
    if alphabet is None:
        alphabet = "".join(sorted(set(password)))
    return len(password) * math.log2(max(len(alphabet), 2))


def _char_kinds(password: str) -> int:
    """统计密码覆盖的字符类别数（小写/大写/数字/符号）。"""
    kinds = set()
    for c in password:
        if c.islower():
            kinds.add("lower")
        elif c.isupper():
            kinds.add("upper")
        elif c.isdigit():
            kinds.add("digit")
        else:
            kinds.add("symbol")
    return len(kinds)


def password_strength(password: str) -> str:
    """主密码强度分级：'weak' | 'ok' | 'strong'。

    简单启发式（P5 用于拒绝弱主密码）：
    - strong: 长度 >= 16 且覆盖 >= 3 类字符
    - ok:     长度 >= 10 且覆盖 >= 2 类字符
    - weak:   其余
    """
    length = len(password)
    kinds = _char_kinds(password)
    if length >= 16 and kinds >= 3:
        return "strong"
    if length >= 10 and kinds >= 2:
        return "ok"
    return "weak"
