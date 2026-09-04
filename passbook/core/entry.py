"""条目模型。

所有敏感字段（title/username/password/url/notes/tags/自定义字段）
统一放在 data 字典里，随整个 payload 一起加密 —— 借鉴 Bitwarden
Cipher 的"type + 不透明加密 JSON"设计，新增条目类型不改表结构，
也不会出现"只加密密码、URL 明文泄露"的经典错误。
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

ENTRY_TYPES = ("login", "note", "card", "identity")
# login: 账号密码 | note: 安全笔记 | card: 银行卡/信用卡 | identity: 身份信息

# 登录账号形态的中文标签（仅展示用；存储一律用 username 字段）
ACCOUNT_KIND_LABELS = {
    "email": "邮箱",
    "phone": "手机号",
    "username": "用户名",
    "empty": "账号",
}
# 录入时的占位提示，随输入内容切换
ACCOUNT_KIND_PLACEHOLDERS = {
    "email": "例如 name@example.com",
    "phone": "例如 13800000000",
    "username": "用户名登录",
    "empty": "邮箱 / 手机号 / 用户名均可",
}

_CN_MOBILE = re.compile(r"1[3-9]\d{9}")  # 大陆手机号：1 开头 11 位


def login_account_kind(value: str) -> str:
    """粗判登录账号的常见形态：'email' / 'phone' / 'username' / 'empty'。

    刻意宽严适度：含 @ 才算邮箱；必须严格匹配大陆手机号格式才算手机号
    （避免把 QQ 号这类纯数字用户名误判）；其余归用户名。

    只服务展示与录入提示，**不参与存储与搜索**——登录标识一律存 username 字段，
    导入导出、搜索、格式全都不受影响。
    """
    v = (value or "").strip()
    if not v:
        return "empty"
    if "@" in v:
        return "email"
    if _CN_MOBILE.fullmatch(v):
        return "phone"
    return "username"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Entry:
    type: str = "login"
    data: dict = field(default_factory=dict)
    folder_id: str | None = None
    favorite: bool = False
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    deleted_at: str | None = None

    def __post_init__(self) -> None:
        if self.type not in ENTRY_TYPES:
            raise ValueError(f"未知条目类型：{self.type}")

    # ---- 常用字段便捷访问（底层仍是 data 字典）----
    @property
    def title(self) -> str:
        return str(self.data.get("title", ""))

    def touch(self) -> None:
        self.updated_at = now_iso()

    # ---- 序列化 ----
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "folder_id": self.folder_id,
            "favorite": self.favorite,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Entry":
        return cls(
            id=d["id"],
            type=d["type"],
            folder_id=d.get("folder_id"),
            favorite=bool(d.get("favorite", False)),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            deleted_at=d.get("deleted_at"),
            data=d.get("data", {}),
        )
