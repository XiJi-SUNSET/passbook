"""CLI 测试：全流程走查（init/add/list/get/search/edit/rm/export/import/passwd）。

交互输入通过替换模块级 _ask_password / _prompt 注入，真实落盘到 tmp_path。
"""

import sys

import pytest

import passbook.cli as cli

MASTER = "MasterPass!123"


class FakeInputs:
    """按顺序返回预设答案，耗尽后返回空字符串。"""

    def __init__(self, *answers):
        self.answers = list(answers)

    def __call__(self, *args, **kwargs):
        return self.answers.pop(0) if self.answers else ""


class FakeClipboard:
    content = ""

    @classmethod
    def copy(cls, text):
        cls.content = text

    @classmethod
    def paste(cls):
        return cls.content


@pytest.fixture(autouse=True)
def _auto_mock_prompt(monkeypatch):
    """默认替换 _prompt 为空输入，避免意外真读 stdin；需要特定答案的测试再显式覆盖。"""
    monkeypatch.setattr(cli, "_prompt", FakeInputs())


@pytest.fixture
def vault_file(tmp_path):
    return tmp_path / "v.pbk"


def _init(vault_file, monkeypatch, password=MASTER):
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(password, password))
    assert cli.main(["init", "-f", str(vault_file)]) == 0


def test_init_creates_vault(vault_file, monkeypatch):
    _init(vault_file, monkeypatch)
    assert vault_file.exists()
    # 内容不是明文 JSON，而是加密二进制
    raw = vault_file.read_bytes()
    assert b"MasterPass" not in raw


def test_init_existing_file_rejected(vault_file, monkeypatch):
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER, MASTER))
    assert cli.main(["init", "-f", str(vault_file)]) == 1


def test_init_weak_password_refused(vault_file, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_ask_password", FakeInputs("12345", "12345"))
    monkeypatch.setattr(cli, "_prompt", FakeInputs(""))  # 对"仍要使用？"答 N
    assert cli.main(["init", "-f", str(vault_file)]) == 1
    assert not vault_file.exists()


def test_wrong_password_fails(vault_file, monkeypatch, capsys):
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs("wrong-pass"))
    assert cli.main(["-f", str(vault_file), "list"]) == 1
    assert "错误" in capsys.readouterr().err


def test_add_list_get_flow(vault_file, monkeypatch, capsys):
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    r = cli.main(
        ["-f", str(vault_file), "add", "--title", "GitHub", "--username", "xi",
         "--password", "p@ss", "--folder", "工作"]
    )
    assert r == 0
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "list"]) == 0
    assert "GitHub" in capsys.readouterr().out
    # get 默认隐藏密码
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "get", "GitHub"]) == 0
    out = capsys.readouterr().out
    assert "p@ss" not in out
    assert "●" in out
    # --show 显示明文
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "get", "GitHub", "--show"]) == 0
    assert "p@ss" in capsys.readouterr().out


def test_add_login_url_and_notes_are_saved(vault_file, monkeypatch, capsys):
    """回归：--url / --notes 曾经被 add 的 login 分支静默丢弃。"""
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    r = cli.main(
        ["-f", str(vault_file), "add", "--title", "GitHub", "--username", "xi",
         "--password", "p@ss", "--url", "https://github.com", "--notes", "主账号"]
    )
    assert r == 0
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "get", "GitHub", "--show"]) == 0
    out = capsys.readouterr().out
    assert "https://github.com" in out
    assert "主账号" in out
    # url 落库后应可被搜索命中
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "search", "github.com"]) == 0
    assert "GitHub" in capsys.readouterr().out


def test_get_copy_password(vault_file, monkeypatch):
    _init(vault_file, monkeypatch)
    monkeypatch.setitem(sys.modules, "pyperclip", FakeClipboard)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "add", "--title", "X", "--password", "secret"])
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "get", "X", "--copy"]) == 0
    assert FakeClipboard.content == "secret"


def test_search_and_folders(vault_file, monkeypatch, capsys):
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "add", "--title", "GitHub", "--folder", "工作"])
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "add", "--title", "阿里云", "--folder", "工作"])
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "search", "github"]) == 0
    assert "GitHub" in capsys.readouterr().out
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "folders"]) == 0
    assert "工作：2 条" in capsys.readouterr().out


def test_edit_flow(vault_file, monkeypatch, capsys):
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "add", "--title", "GitHub", "--password", "p1"])
    # edit：改 title，其余回车保留；密码回车不变
    monkeypatch.setattr(cli, "_prompt", FakeInputs("GitHub2", "", "", "", ""))
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER, ""))
    assert cli.main(["-f", str(vault_file), "edit", "GitHub"]) == 0
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "get", "GitHub2", "--show"])
    out = capsys.readouterr().out
    assert "p1" in out  # 密码未变
    assert "GitHub2" in out


def test_rm_restore_purge_flow(vault_file, monkeypatch, capsys):
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "add", "--title", "Temp"])
    # 软删 → 回收站可见
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "rm", "Temp"]) == 0
    capsys.readouterr()  # 清掉 add/rm 的输出，只留 list 结果
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "list", "--trash"])
    out = capsys.readouterr().out
    assert "Temp" in out
    prefix = out.split()[0]  # 第一列是 id 前缀
    # 前缀恢复
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "restore", prefix]) == 0
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "list"])
    assert "Temp" in capsys.readouterr().out
    # 再删 → purge 前缀
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "rm", "Temp"])
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "purge", "Temp"]) == 0
    capsys.readouterr()  # 清掉 rm/purge 输出
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "list", "--trash"])
    assert "Temp" not in capsys.readouterr().out


def test_export_import_json_roundtrip(vault_file, tmp_path, monkeypatch, capsys):
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "add", "--title", "GitHub", "--folder", "工作"])
    out_json = tmp_path / "e.json"
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "export", "json", "-o", str(out_json)]) == 0
    data = out_json.read_text(encoding="utf-8")
    assert "passbook-export" in data
    assert "GitHub" in data
    # 导入到新库（合并）
    f2 = tmp_path / "v2.pbk"
    _init(f2, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(f2), "import", str(out_json)]) == 0
    assert "已导入 1 条" in capsys.readouterr().out
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(f2), "list"])
    assert "GitHub" in capsys.readouterr().out


def test_export_csv_and_import(vault_file, tmp_path, monkeypatch, capsys):
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "add", "--title", "GitHub",
              "--username", "xi", "--password", "p@ss"])
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "export", "csv"]) == 0
    out = capsys.readouterr().out
    assert "name,url,username,password,note" in out.splitlines()
    assert "GitHub" in out
    # Chrome 导出的 CSV 直接导入
    chrome_csv = tmp_path / "chrome.csv"
    chrome_csv.write_text(
        "name,url,username,password,note\n"
        "B站,https://bilibili.com,up主,secret123,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "import", str(chrome_csv), "--folder", "视频"]) == 0
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "search", "B站"])
    assert "B站" in capsys.readouterr().out


def test_gen_command(capsys):
    assert cli.main(["gen", "--len", "12"]) == 0
    out = capsys.readouterr().out.strip().splitlines()[0]
    assert len(out) == 12
    assert cli.main(["gen", "--len", "8", "--no-symbols", "--no-upper"]) == 0
    pw = capsys.readouterr().out.strip().splitlines()[0]
    assert len(pw) == 8
    assert pw.islower() or pw.isdigit()


def test_passwd_flow(vault_file, monkeypatch, capsys):
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(
        cli, "_ask_password",
        FakeInputs(MASTER, "NewPass!2026", "NewPass!2026"),
    )
    assert cli.main(["-f", str(vault_file), "passwd"]) == 0
    # 旧密码失效
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "list"]) == 1
    # 新密码可用
    monkeypatch.setattr(cli, "_ask_password", FakeInputs("NewPass!2026"))
    assert cli.main(["-f", str(vault_file), "list"]) == 0


def test_lock_and_no_command(capsys):
    assert cli.main(["lock"]) == 0
    assert "无需" in capsys.readouterr().out
    assert cli.main([]) == 1  # 无命令 → 打印 help


# ---------- 打包 exe 双击启动的交互模式 ----------
def _repl(monkeypatch, lines):
    """模拟"双击 exe"：frozen=True 且 argv 为空，交互输入由 lines 提供。"""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "argv", ["passbook.exe"])
    monkeypatch.setattr("builtins.input", FakeInputs(*lines))
    return cli.main(None)


def test_repl_enters_interactive_instead_of_flashing(monkeypatch, capsys):
    """双击 exe 无参数时不能 print_help 完就退——那正是"窗口一闪而过"的根因。"""
    assert _repl(monkeypatch, ["exit"]) == 0
    out = capsys.readouterr().out
    assert "密码本" in out
    assert "库文件" in out


def test_repl_runs_real_commands(monkeypatch, capsys):
    assert _repl(monkeypatch, ["gen --len 8", "exit"]) == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l]
    assert any(len(l) == 8 and l.isprintable() for l in lines)


def test_repl_survives_bad_command(monkeypatch, capsys):
    """输错命令时 argparse 会 SystemExit，交互模式必须吞掉并继续。"""
    assert _repl(monkeypatch, ["no-such-cmd", "exit"]) == 0


def test_repl_strips_bom_from_pasted_command(monkeypatch, capsys):
    """从网页粘贴的命令可能带 BOM，不清掉会被当成子命令名报 invalid choice。"""
    assert _repl(monkeypatch, ["\ufeffgen --len 8", "exit"]) == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l]
    assert any(len(l) == 8 and l.isprintable() for l in lines)


def test_repl_has_no_vault_switch_entry(monkeypatch, capsys):
    """库位置固定，不提供 use 之类的切换入口；误输入也不会崩，只当未知命令处理。"""
    assert _repl(monkeypatch, ['use "D:\\x.pbk"', "exit"]) == 0
    assert "切换到" not in capsys.readouterr().out


def test_file_flag_hidden_from_help_but_usable(vault_file, monkeypatch, capsys):
    """-f 对使用者隐藏（不提供选位置），但测试与应急仍可用。"""
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    help_text = capsys.readouterr().out
    assert "--file" not in help_text
    assert "-f FILE" not in help_text

    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    assert cli.main(["-f", str(vault_file), "list"]) == 0


def test_no_args_still_prints_help_when_not_frozen(monkeypatch, capsys):
    """命令行（非打包）下无参数仍应打印 help 并返回 1，保持脚本可判断用法错误。"""
    assert cli.main([]) == 1
    assert "usage" in capsys.readouterr().out


def test_add_interactive(vault_file, monkeypatch, capsys):
    _init(vault_file, monkeypatch)
    monkeypatch.setattr(cli, "_prompt", FakeInputs("交互条目", "user1"))
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER, "pw1"))
    assert cli.main(["-f", str(vault_file), "add"]) == 0
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(MASTER))
    cli.main(["-f", str(vault_file), "get", "交互条目", "--show"])
    assert "pw1" in capsys.readouterr().out
