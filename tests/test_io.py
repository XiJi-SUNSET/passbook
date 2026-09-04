"""导入导出测试：CSV/JSON 格式、列名容错、缺列报错、JSON 还原。"""

import pytest

from passbook.core.entry import Entry
from passbook.core.vault import Folder, Vault
from passbook.io.exporter import export_csv, export_json
from passbook.io.importer import parse_chrome_csv, parse_passbook_json


def _vault_with_data() -> Vault:
    v = Vault()
    f = v.add_folder("工作")
    v.add_entry(
        Entry(
            type="login",
            folder_id=f.id,
            data={
                "title": "GitHub",
                "url": "https://github.com",
                "username": "xi,ji",  # 含逗号，验证 CSV 转义
                "password": "p@ss,word",
                "notes": "含,逗号备注",
            },
        )
    )
    v.add_entry(Entry(type="note", data={"title": "安全笔记", "notes": "机密内容"}))
    return v


def test_export_csv_escapes_formula_injection():
    """以 = + - @ 开头的字段必须加 ' 前缀，防 Excel/Sheets 公式注入。"""
    v = Vault()
    v.add_entry(Entry(type="login", data={
        "title": "=SUM(A1)", "url": "-https://x", "username": "+8613800000000",
        "password": "@cmd", "notes": "普通备注",
    }))
    csv_text = export_csv(v)
    assert "'=SUM(A1)" in csv_text
    assert "'-https://x" in csv_text
    assert "'+8613800000000" in csv_text
    assert "'@cmd" in csv_text
    assert "普通备注" in csv_text  # 普通值不加前缀


def test_export_csv_header_and_rows():
    csv_text = export_csv(_vault_with_data())
    lines = csv_text.strip().splitlines()
    assert lines[0] == "name,url,username,password,note"
    # 只有 login 条目进 CSV，note 不出现
    assert "GitHub" in csv_text
    assert "安全笔记" not in csv_text


def test_export_csv_roundtrip_parse():
    v = _vault_with_data()
    entries = parse_chrome_csv(export_csv(v))
    assert len(entries) == 1
    e = entries[0]
    assert e.type == "login"
    assert e.data["title"] == "GitHub"
    assert e.data["username"] == "xi,ji"  # 逗号被正确还原
    assert e.data["password"] == "p@ss,word"


def test_export_json_structure():
    v = _vault_with_data()
    data = parse_passbook_json(export_json(v))
    assert data["format"] == "passbook-export"
    assert len(data["folders"]) == 1
    assert len(data["entries"]) == 2  # 未删条目全部导出（含 note）


def test_export_json_excludes_trash_by_default():
    v = _vault_with_data()
    e = v.list_active()[0]
    v.soft_delete(e.id)
    data = parse_passbook_json(export_json(v))
    assert len(data["entries"]) == 1
    data2 = parse_passbook_json(export_json(v, include_trash=True))
    assert len(data2["entries"]) == 2


def test_parse_chrome_csv_field_aliases():
    # 新版 Chrome 可能多出其他列，列名大小写/别名需容错
    text = (
        "name,url,user,password,note,extra\n"
        "B站,https://bilibili.com,up主,secret,,xx\n"
    )
    entries = parse_chrome_csv(text)
    assert entries[0].data["username"] == "up主"
    assert entries[0].data["url"] == "https://bilibili.com"


def test_parse_chrome_csv_missing_password_raises():
    with pytest.raises(ValueError):
        parse_chrome_csv("name,url,username\nxx,https://x.com,u\n")


def test_parse_chrome_csv_empty_title_falls_back_to_url():
    entries = parse_chrome_csv("name,url,username,password\n,https://x.com,u,p\n")
    assert entries[0].data["title"] == "https://x.com"


def test_parse_chrome_csv_empty_rows_returns_empty():
    assert parse_chrome_csv("name,url,username,password,note\n") == []


def test_parse_passbook_json_rejects_foreign_file():
    with pytest.raises(ValueError):
        parse_passbook_json('{"format": "other", "entries": []}')
