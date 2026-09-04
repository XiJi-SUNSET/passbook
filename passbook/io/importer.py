"""导入：Chrome/Edge 导出的 CSV（合并）+ passbook JSON 导出（合并还原）。"""

import csv
import io
import json

from ..core.entry import Entry


def parse_chrome_csv(text: str) -> list[Entry]:
    """解析 Chrome/Edge 导出的 CSV，返回 login 条目列表。

    列名容错（新旧版本差异）：name/title → 标题，url → 链接，
    username/user/login_username → 用户名，password → 密码，note/notes → 备注。
    缺少 password 列直接报错（没有密码的导入没有意义）。
    """
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    first = rows[0]

    def pick(*names):
        return next((n for n in names if n in first), None)

    c_title = pick("name", "title")
    c_url = pick("url")
    c_user = pick("username", "user", "login_username")
    c_pass = pick("password")
    c_note = pick("note", "notes")
    if c_pass is None:
        raise ValueError("CSV 缺少 password 列，无法导入")

    entries = []
    for row in rows:
        title = (row.get(c_title) or "").strip()
        url = (row.get(c_url) or "").strip()
        if not title:
            title = url or "未命名"
        entries.append(
            Entry(
                type="login",
                data={
                    "title": title,
                    "url": url,
                    "username": (row.get(c_user) or "").strip(),
                    "password": row.get(c_pass) or "",
                    "notes": (row.get(c_note) or "").strip(),
                },
            )
        )
    return entries


def parse_passbook_json(text: str) -> dict:
    """解析 passbook JSON 导出，返回 {"folders": [...], "entries": [...]}。

    不做 id 去重/合并，合并策略由调用方（CLI 合并进现有库）决定。
    """
    data = json.loads(text)
    if not isinstance(data, dict) or data.get("format") != "passbook-export":
        raise ValueError("不是 passbook 导出文件（缺少 passbook-export 标记）")
    return data
