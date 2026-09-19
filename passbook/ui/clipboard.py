"""GUI 剪贴板：复制并在 45 秒后自动清空（仅当内容未被改写）。

CLI 用不了这套：一次性命令返回后进程立即退出，QTimer/线程定时器都不会
幸存，那边的清空由用户按回车触发（见 cli._copy_password_interactive）。
两套实现对应两种进程模型，刻意不强行统一。
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

COPY_CLEAR_MS = 45_000  # 与界面文案"45 秒后自动清空"一致


def copy_with_auto_clear(text: str) -> None:
    """复制到剪贴板；45 秒后若内容仍是它则清空（用户复制了别的则不误清）。"""
    clipboard = QApplication.clipboard()
    clipboard.setText(text)

    def _clear() -> None:
        if clipboard.text() == text:
            clipboard.clear()

    QTimer.singleShot(COPY_CLEAR_MS, _clear)
