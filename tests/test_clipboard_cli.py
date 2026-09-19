"""CLI 剪贴板行为（审计 P0-1 回归）。

一次性命令返回后进程立即退出，任何定时器都不会执行——"45 秒后自动清空"
曾经是句谎话。现在：复制后等用户按回车清空（内容被改写则不误清）；
非交互输入（管道/脚本）明确告知不会自动清空，不再假装。
"""

import io
import sys

import pytest

import passbook.cli as cli
from tests.test_cli import FakeClipboard, FakeInputs

MASTER = "MasterPass!123"


class TtyStdin:
    """让 sys.stdin.isatty() 返回 True 的替身（模拟真实终端）。"""

    @staticmethod
    def isatty() -> bool:
        return True


@pytest.fixture
def vault_file(tmp_path, monkeypatch):
    f = tmp_path / "v.pbk"
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER, MASTER))
    monkeypatch.setattr(cli, "_prompt", FakeInputs())  # add 的 用户名/链接 追问
    assert cli.main(["init", "-f", str(f)]) == 0
    monkeypatch.setitem(sys.modules, "pyperclip", FakeClipboard)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(f), "add", "--title", "X", "--password", "secret"]) == 0
    FakeClipboard.content = ""
    return f


def _get_copy(vault_file, monkeypatch) -> int:
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    return cli.main(["-f", str(vault_file), "get", "X", "--copy"])


def test_copy_clears_after_enter(vault_file, monkeypatch, capsys):
    """交互模式：复制成功，用户回车后清空。"""
    monkeypatch.setattr(sys, "stdin", TtyStdin())
    monkeypatch.setattr("builtins.input", FakeInputs(""))
    assert _get_copy(vault_file, monkeypatch) == 0
    assert FakeClipboard.content == ""
    assert "剪贴板已清空" in capsys.readouterr().out


def test_copy_keeps_content_if_user_copied_something_else(vault_file, monkeypatch, capsys):
    """回车前用户复制了别的内容：不误清。"""
    monkeypatch.setattr(sys, "stdin", TtyStdin())

    def _replace_then_enter(*_a, **_k):
        FakeClipboard.content = "用户自己复制的内容"
        return ""

    monkeypatch.setattr("builtins.input", _replace_then_enter)
    assert _get_copy(vault_file, monkeypatch) == 0
    assert FakeClipboard.content == "用户自己复制的内容"
    assert "已被改写" in capsys.readouterr().out


def test_copy_noninteractive_warns_instead_of_lying(vault_file, monkeypatch, capsys):
    """非交互（管道/脚本）：仍复制，但明确告知进程退出后不会自动清空。"""
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert _get_copy(vault_file, monkeypatch) == 0
    assert FakeClipboard.content == "secret"  # 复制本身照常
    out = capsys.readouterr().out
    assert "非交互" in out
    assert "45 秒后自动清空" not in out
