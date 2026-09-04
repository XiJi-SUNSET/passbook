"""GUI 入口：建库 / 解锁 / 主窗口 的流程编排。

库文件位置固定（paths.vault_path），界面里不提供选择入口。
解锁失败会一直重试并给出原因，不会因为输错一次就退出。
"""

import sys

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ..core.exceptions import CredentialsError, PassbookError, PayloadChecksumError
from ..paths import vault_path
from . import theme
from .dialogs import SetupDialog, UnlockDialog
from .main_window import MainWindow
from .session import Session


def _create_vault(session: Session) -> bool:
    """首次使用：设置主密码建库。"""
    dlg = SetupDialog()
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    try:
        session.create(dlg.password)
    except PassbookError as e:
        QMessageBox.critical(None, "建库失败", str(e))
        return False
    return True


def _unlock(session: Session, path: str) -> bool:
    """反复要求主密码直到成功或用户放弃。"""
    error = ""
    while True:
        dlg = UnlockDialog(path=path, error=error)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            session.unlock(dlg.password)
            return True
        except CredentialsError:
            error = "主密码错误，或库文件已被篡改"
        except PayloadChecksumError:
            error = "数据校验失败，请用 passbook-cli recover 从备份恢复"
        except PassbookError as e:
            error = str(e)


def _disable_ui_animations(app: QApplication) -> None:
    """关掉菜单/下拉的弹出动画——系统动画在这种界面上又慢又卡，直接显示更快更稳。"""
    from PySide6.QtCore import Qt

    for effect in (
        Qt.UIEffect.UI_AnimateMenu,
        Qt.UIEffect.UI_AnimateCombo,
        Qt.UIEffect.UI_FadeMenu,
        Qt.UIEffect.UI_FadeTooltip,
    ):
        app.setEffectEnabled(effect, False)


def run_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("密码本")
    app.setStyleSheet(theme.stylesheet())
    _disable_ui_animations(app)

    path = vault_path()
    session = Session(path)

    if not session.vault_exists():
        if not _create_vault(session):
            return 0
    elif not _unlock(session, path):
        return 0

    while True:
        window = MainWindow(session)
        window.locked.connect(window.close)
        window.show()
        app.exec()
        # 走到这里说明窗口关了或自动锁定了，重新解锁才能看到数据
        if not _unlock(session, path):
            return 0
