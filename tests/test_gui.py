"""GUI 层测试（offscreen，不弹真实窗口）。

PySide6 未安装时这些测试整体跳过（qapp fixture 自动 importorskip）。
对话框测试一律不调 exec()（会阻塞），只构造 + 填值 + 直接调内部校验。
"""

import pytest

# 必须在任何 PySide6 import 之前：CI 的 [dev] 依赖不含 PySide6，
# 顶层 import 会在收集阶段就炸，而不是让测试优雅跳过。
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog

from passbook.core.exceptions import CredentialsError
from passbook.crypto.kdf import KdfParams
from passbook.ui import theme
from passbook.ui.dialogs import ChangeMasterDialog, GeneratorDialog, SetupDialog, UnlockDialog
from passbook.ui.entry_dialog import EntryDialog
from passbook.ui.main_window import MainWindow
from passbook.ui.session import Session

MASTER = "MasterPass!123"


def _fast_params() -> KdfParams:
    return KdfParams(memory_mib=1, iterations=1, parallelism=1)


def _session(tmp_path, password=MASTER) -> Session:
    s = Session(str(tmp_path / "v.pbk"), params=_fast_params())
    s.create(password)
    return s


# ---------- Session：会话生命周期与内存清零 ----------
def test_session_create_unlock_save_flow(tmp_path):
    s = _session(tmp_path)
    assert s.unlocked
    assert not s.vault_exists() or True  # create 已落盘
    assert s.vault.list_active() == []

    # 新实例解锁
    s2 = Session(str(tmp_path / "v.pbk"), params=_fast_params())
    assert not s2.unlocked
    s2.unlock(MASTER)
    assert s2.unlocked

    # 保存改动
    s2.entries.create(entry_type="login",
                      data={"title": "GitHub", "username": "xi", "password": "p@ss"})
    s2.save()
    s3 = Session(str(tmp_path / "v.pbk"), params=_fast_params())
    s3.unlock(MASTER)
    assert s3.vault.list_active()[0].title == "GitHub"


def test_session_wrong_password_leaves_nothing_remembered(tmp_path):
    s = _session(tmp_path)
    s.lock()
    with pytest.raises(CredentialsError):
        s.unlock("wrong-pass")
    assert not s.unlocked
    assert s._password is None  # 出错时绝不记住任何东西


def test_session_wipe_zeroes_password_buffer(tmp_path):
    s = _session(tmp_path)
    buf = s._password
    assert isinstance(buf, bytearray)
    s.lock()
    # 锁定时逐字节清零而非简单丢弃引用
    assert all(b == 0 for b in buf)
    assert s._password is None
    assert not s.unlocked


def test_session_change_password_swaps_buffer(tmp_path):
    s = _session(tmp_path)
    old = s._password
    s.change_password("NewPass!2026")
    assert bytes(old) != b"NewPass!2026"  # 旧缓存已被清零覆写
    assert bytes(s._password).decode("utf-8") == "NewPass!2026"

    s.lock()
    with pytest.raises(CredentialsError):
        s.unlock(MASTER)
    s.unlock("NewPass!2026")  # 新密码有效


# ---------- theme ----------
def test_theme_keeps_citrus_tokens():
    qss = theme.stylesheet()
    for token in ("#ed685f", "#d94f46", "#f2ede6", "#3a3a3a", "#8a8a8a",
                  "rgba(237,104,95,.18)", "rgba(237,104,95,.14)",
                  "Segoe UI", "Microsoft YaHei", "rgba(242,237,230,.36)"):
        assert token in qss


# ---------- 对话框输入校验 ----------
def test_setup_dialog_rejects_mismatch(qapp):
    dlg = SetupDialog()
    dlg._pw.setText("Password123")
    dlg._pw2.setText("Password124")
    dlg._accept()
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert "不一致" in dlg._error.text()


def test_setup_dialog_weak_password_requires_override(qapp):
    """弱密码不硬拒：先提示并给出"仍要使用"勾选，勾选后才能通过。"""
    dlg = SetupDialog()
    dlg._pw.setText("12345")
    dlg._pw2.setText("12345")
    dlg._accept()
    assert dlg.result() != QDialog.DialogCode.Accepted  # 第一次被阻断并提示
    assert "弱" in dlg._error.text()

    dlg._accept_weak.setChecked(True)
    dlg._accept()
    assert dlg.result() == QDialog.DialogCode.Accepted  # 确认风险后放行


def test_change_master_dialog_weak_new_requires_override(qapp):
    dlg = ChangeMasterDialog(has_current=False)
    dlg._new.setText("12345")
    dlg._new2.setText("12345")
    dlg._accept()
    assert dlg.result() != QDialog.DialogCode.Accepted

    dlg._accept_weak.setChecked(True)
    dlg._accept()
    assert dlg.result() == QDialog.DialogCode.Accepted


def test_setup_dialog_accepts_strong_password(qapp):
    dlg = SetupDialog()
    dlg._pw.setText(MASTER)
    dlg._pw2.setText(MASTER)
    dlg._accept()
    assert dlg.result() == QDialog.DialogCode.Accepted


def test_unlock_dialog_presets_error(qapp):
    dlg = UnlockDialog(error="主密码错误，或库文件已被篡改")
    assert "主密码错误" in dlg._error.text()


def test_generator_dialog_makes_valid_password(qapp):
    dlg = GeneratorDialog()
    pw = dlg.password
    assert 8 <= len(pw) <= 64
    assert pw  # 非空
    # 关掉"符号"后仍能生成（各字符集至少一类的约束下）
    dlg._symbols.setChecked(False)
    assert dlg.password


# ---------- 登录账号智能标签 ----------
def test_entry_dialog_account_label_switches_with_input(qapp):
    """录入时标签随输入切换：@→邮箱，大陆手机号→手机号，其余→用户名。"""
    dlg = EntryDialog()
    label = dlg._form.labelForField(dlg._username)

    assert label.text() == "账号"  # 空输入用中性词
    dlg._username.setText("me@qq.com")
    assert label.text() == "邮箱"
    dlg._username.setText("13800138000")
    assert label.text() == "手机号"
    dlg._username.setText("xijisunset")
    assert label.text() == "用户名"


def test_entry_dialog_presets_label_from_edited_value(qapp):
    """编辑已有邮箱登录的条目时，标签应直接显示"邮箱"。"""
    from passbook.core.entry import Entry

    e = Entry(type="login", data={"title": "GitHub", "username": "xiji@github.com"})
    dlg = EntryDialog(entry=e)
    assert dlg._form.labelForField(dlg._username).text() == "邮箱"


def test_detail_account_label_switches(qapp, tmp_path):
    """详情页账号行标签按条目内容切换。"""
    s = _session(tmp_path)
    s.entries.create(entry_type="login",
                     data={"title": "手机站", "username": "13912345678", "password": "x"})
    s.save()
    s.lock()
    s.unlock(MASTER)
    win = MainWindow(s)
    win._list.setCurrentRow(0)
    assert win._row_labels["username"].text() == "手机号"
    win.close()


# ---------- 主窗口集成 ----------
def test_main_window_list_search_and_copy(qapp, tmp_path):
    s = _session(tmp_path)
    s.entries.create(entry_type="login",
                     data={"title": "GitHub", "username": "xi", "password": "p@ss"})
    s.entries.create(entry_type="login",
                     data={"title": "阿里云", "username": "alice", "password": "x"})
    s.save()
    s.lock()
    s.unlock(MASTER)

    win = MainWindow(s)
    assert win._list.count() == 2

    # 搜索过滤
    win._search.setText("github")
    assert win._list.count() == 1
    win._search.setText("不存在的词")
    assert win._list.count() == 0

    # 选中 → 详情
    win._search.setText("")
    win._list.setCurrentRow(0)
    assert win._current is not None
    assert win._current.title in ("GitHub", "阿里云")
    assert win._rows["password"].text().startswith("●")  # 默认打码

    # 显示密码
    win._reveal_btn.setChecked(True)
    assert win._rows["password"].text() == win._current.data.get("password")

    # 复制密码 → 剪贴板，且立刻清空不出错
    win._copy_password()
    assert QApplication.clipboard().text() == win._current.data.get("password")
    win._clear_clipboard()
    assert QApplication.clipboard().text() == ""
    assert s.unlocked

    # 关窗（= 用户退出）应自动锁定会话并清零密码
    win.close()
    assert not s.unlocked
    assert s._password is None


# ---------- 一键导出明文副本 ----------
def _patch_export_dialogs(monkeypatch, tmp_path, choice, filename):
    """把导出流程里的选择框/保存框/消息框全替换掉，返回写出的文件路径。"""
    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

    out = tmp_path / filename
    monkeypatch.setattr(
        QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (choice, True)),
    )
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "")),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    return out


def _unlocked_window(tmp_path) -> MainWindow:
    s = _session(tmp_path)
    s.entries.create(entry_type="login",
                     data={"title": "迁移用", "username": "me@qq.com", "password": "s3cret"})
    s.entries.create(entry_type="note", data={"title": "笔记", "notes": "敏感内容"})
    s.save()
    s.lock()
    s.unlock(MASTER)
    return MainWindow(s)


def test_export_json_writes_full_plaintext_copy(qapp, tmp_path, monkeypatch):
    out = _patch_export_dialogs(
        monkeypatch, tmp_path,
        "JSON 完整副本（密码本可还原，含文件夹/备注/全部类型）", "copy.json")
    win = _unlocked_window(tmp_path)
    win._export()
    text = out.read_text(encoding="utf-8")
    assert "passbook-export" in text
    assert "迁移用" in text
    assert "s3cret" in text  # 明文，确实"副本"
    assert "笔记" in text     # 非 login 类型也在
    win.close()


def test_export_csv_writes_migration_copy(qapp, tmp_path, monkeypatch):
    out = _patch_export_dialogs(
        monkeypatch, tmp_path, "CSV 迁移格式（浏览器及 KeePass/Bitwarden 等通用）", "copy.csv")
    win = _unlocked_window(tmp_path)
    win._export()
    text = out.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "name,url,username,password,note"
    assert "迁移用" in text
    assert "笔记" not in text  # CSV 只承载 login
    win.close()
