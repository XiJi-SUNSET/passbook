"""导出：JSON（备份/迁移，完整还原）+ CSV（Chrome/Edge 兼容）。

安全约定：
- 导出是**明文**操作，只在保险库解锁状态下由用户主动发起。
- CSV 走 Chrome/Edge 密码导入格式（name,url,username,password,note），
  可以反向导入浏览器；JSON 走完整结构，可还原到 passbook。
"""

import csv
import io
import json

from ..core.entry import now_iso
from ..core.vault import Vault

EXPORT_FORMAT = "passbook-export"
EXPORT_VERSION = 1

# Chrome/Edge 密码导出列名
CSV_HEADERS = ["name", "url", "username", "password", "note"]

# CSV 公式注入防护：这些前缀被 Excel/Sheets 当作公式执行
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value) -> str:
    """给危险前缀字段加单引号，防 CSV 公式注入。

    代价：极少数以 = + - @ 开头的值（如标题）走浏览器导入时会带上 ' 前缀，
    但换来了"用 Excel/Sheets 打开导出文件不会执行公式"的安全底线。
    """
    v = str(value)
    if v.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + v
    return v


def export_json(vault: Vault, include_trash: bool = False) -> str:
    """导出完整结构（folders + entries），可用于备份或迁移到另一台机器。"""
    entries = [e for e in vault.entries if include_trash or e.deleted_at is None]
    payload = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": now_iso(),
        "folders": [f.to_dict() for f in vault.folders],
        "entries": [e.to_dict() for e in entries],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def export_csv(vault: Vault) -> str:
    """导出 login 条目为 Chrome/Edge 可导入的 CSV。

    仅含账号密码类条目；note/card/identity 与文件夹结构不进 CSV
    （浏览器格式承载不了），需要完整备份请用 export json。
    """
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_HEADERS)
    for e in vault.list_active():
        if e.type != "login":
            continue
        writer.writerow(
            [_csv_safe(e.data.get(k, "")) for k in
             ("title", "url", "username", "password", "notes")]
        )
    return out.getvalue()
