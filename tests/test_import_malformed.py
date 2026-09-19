"""畸形数据不裸奔（审计 P2 回归）：缺字段必须翻译成可行动的 PassbookError。

- 库文件字段缺失 → FormatError（"库文件结构不完整"，用户知道该走 recover）
- 导入文件字段缺失 → "第 N 条缺少必需字段"（能定位到具体条目）
"""

import json

import pytest

from passbook.core.exceptions import FormatError
from passbook.core.vault import Vault
from passbook.format.writer import save


# ---------- 库文件：Vault.from_dict ----------
def test_vault_from_dict_missing_entry_field():
    with pytest.raises(FormatError, match="结构不完整"):
        Vault.from_dict({"format_version": 1, "folders": [], "entries": [{"id": "x"}]})


def test_vault_from_dict_missing_folder_field():
    with pytest.raises(FormatError, match="结构不完整"):
        Vault.from_dict({"format_version": 1, "folders": [{"name": "f"}], "entries": []})


def test_vault_from_dict_not_a_dict():
    with pytest.raises(FormatError, match="结构不完整"):
        Vault.from_dict(["not", "a", "dict"])


def test_vault_from_dict_bad_version_type():
    with pytest.raises(FormatError, match="format_version"):
        Vault.from_dict({"format_version": "abc", "folders": [], "entries": []})


# ---------- CLI 端到端 ----------
def test_cli_reports_malformed_vault_without_traceback(
    vault_path, fast_params, monkeypatch, capsys
):
    """能正常解密、但条目缺字段的库：CLI 应报错并指向 recover，而不是裸 KeyError。"""
    import passbook.cli as cli
    from tests.test_cli import FakeInputs

    payload = json.dumps(
        {"format_version": 1, "folders": [], "entries": [{"id": "x"}]}
    ).encode("utf-8")
    save(vault_path, "MasterPass!123", payload, params=fast_params)

    monkeypatch.setattr(cli, "_ask_password", FakeInputs("MasterPass!123"))
    assert cli.main(["-f", vault_path, "list"]) == 1
    err = capsys.readouterr().err
    assert "结构不完整" in err
    assert "Traceback" not in err


def test_cli_import_json_missing_id_is_locatable(
    vault_path, fast_params, tmp_path, monkeypatch, capsys
):
    """导入 JSON 的条目缺 id：报"第 1 条"，而不是裸 KeyError。"""
    import passbook.cli as cli
    from tests.test_cli import FakeInputs

    save(
        vault_path,
        "MasterPass!123",
        b'{"format_version": 1, "folders": [], "entries": []}',
        params=fast_params,
    )
    src = tmp_path / "bad.json"
    src.write_text(
        json.dumps(
            {
                "format": "passbook-export",
                "version": 1,
                "folders": [],
                "entries": [{"type": "login", "data": {"title": "无 id"}}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_ask_password", FakeInputs("MasterPass!123"))
    assert cli.main(["-f", vault_path, "import", str(src)]) == 1
    err = capsys.readouterr().err
    assert "第 1 条" in err
    assert "Traceback" not in err
