"""CSV 往返保真（审计 P0-2 回归）。

背景：防公式注入的 ' 前缀曾被无差别加到 password 列，导出再导入后
密码会变成 "' -Passw0rd!" 这种值，用户直接登录不上。密码列必须原样输出。
"""

import pytest

from passbook.core.entry import Entry
from passbook.core.vault import Vault
from passbook.io.exporter import export_csv
from passbook.io.importer import parse_chrome_csv


@pytest.mark.parametrize(
    "password",
    [
        "=SUM(A1)",
        "+8613800000000",
        "-Passw0rd!",
        "@home2026",
        "普通密码123",
        '有,逗号"引号',
    ],
)
def test_csv_password_roundtrip_is_exact(password):
    v = Vault()
    v.add_entry(
        Entry(
            type="login",
            data={
                "title": "站点",
                "url": "https://x",
                "username": "u",
                "password": password,
            },
        )
    )
    [entry] = parse_chrome_csv(export_csv(v))
    assert entry.data["password"] == password


def test_csv_other_columns_keep_injection_guard():
    """展示列仍加 ' 前缀（Excel/Sheets 打开安全），只有密码列例外。"""
    v = Vault()
    v.add_entry(
        Entry(
            type="login",
            data={
                "title": "=SUM(A1)",
                "url": "-https://x",
                "username": "+8613800000000",
                "password": "@cmd",
                "notes": "普通备注",
            },
        )
    )
    csv_text = export_csv(v)
    assert "'=SUM(A1)" in csv_text
    assert "'-https://x" in csv_text
    assert "'+8613800000000" in csv_text
    assert "@cmd" in csv_text
    assert "'@cmd" not in csv_text  # 密码没有被加前缀
