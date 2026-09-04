"""建库 / 解锁 / 改主密码 / 生成密码 对话框。

只负责收集输入与提示，任何业务动作都由调用方拿结果去执行，
这样这些对话框不依赖 Session，也容易单独测。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..services.generator import generate, password_strength
from . import theme

_MIN_MASTER_LEN_HINT = "建议 ≥ 10 位且含大小写与数字"


class _BaseDialog(QDialog):
    def __init__(self, parent=None, title: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(380)
        self._error = QLabel("")
        self._error.setProperty("dim", False)
        self._error.setStyleSheet(f"color: {theme.RED_DARK};")
        self._error.setWordWrap(True)
        self._error.hide()

    def _show_error(self, text: str) -> None:
        self._error.setText(text)
        self._error.show()
        self.adjustSize()

    def _clear_error(self) -> None:
        self._error.hide()

    # ---- 弱密码"仍要使用"确认（主密码强度是建议不是禁令）----
    def _new_weak_override(self) -> QCheckBox:
        """返回一个初始隐藏的"仍要使用"勾选框，需自行 addWidget。"""
        cb = QCheckBox("我知道这个主密码偏弱，仍要使用")
        cb.hide()
        return cb

    def _block_on_weak(self, cb: QCheckBox, reason: str) -> bool:
        """弱密码且未勾选：显示提示，返回 True 阻断本次确认。"""
        if cb.isChecked():
            return False
        cb.show()
        self._show_error(reason)
        return True

    def _reset_weak_override(self, cb: QCheckBox) -> None:
        """用户改动密码后，重置确认状态。"""
        cb.setChecked(False)
        cb.hide()
        self._clear_error()


def _password_field(placeholder: str = "") -> QLineEdit:
    f = QLineEdit()
    f.setEchoMode(QLineEdit.EchoMode.Password)
    f.setPlaceholderText(placeholder)
    return f


class SetupDialog(_BaseDialog):
    """首次使用：设置主密码。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, "创建保险库")
        self._pw = _password_field("主密码")
        self._pw2 = _password_field("再次输入确认")
        self._accept_weak = self._new_weak_override()
        self._pw.textChanged.connect(lambda: self._reset_weak_override(self._accept_weak))
        hint = QLabel(f"库文件将创建在程序旁。{_MIN_MASTER_LEN_HINT}")
        hint.setProperty("dim", True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("创建")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.setSpacing(theme.GAP)
        form.addRow("主密码", self._pw)
        form.addRow("确认", self._pw2)

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.GAP)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self._accept_weak)
        layout.addWidget(self._error)
        layout.addWidget(buttons)

    @property
    def password(self) -> str:
        return self._pw.text()

    def _accept(self) -> None:
        pw, pw2 = self._pw.text(), self._pw2.text()
        if not pw:
            return self._show_error("主密码不能为空")
        if pw != pw2:
            return self._show_error("两次输入不一致")
        if password_strength(pw) == "weak":
            if self._block_on_weak(
                self._accept_weak,
                f"主密码偏弱，容易被暴力破解。{_MIN_MASTER_LEN_HINT}。勾选下方选项可继续。",
            ):
                return
        self._clear_error()
        self.accept()


class UnlockDialog(_BaseDialog):
    """解锁：输入主密码。"""

    def __init__(self, parent=None, path: str = "", error: str = "") -> None:
        super().__init__(parent, "解锁保险库")
        self._pw = _password_field("主密码")
        self._pw.returnPressed.connect(self._accept)
        if error:
            self._show_error(error)

        where = QLabel(f"库文件：{path}")
        where.setProperty("dim", True)
        where.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("解锁")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("退出")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.setSpacing(theme.GAP)
        form.addRow("主密码", self._pw)

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.GAP)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.addLayout(form)
        layout.addWidget(where)
        layout.addWidget(self._error)
        layout.addWidget(buttons)
        self._pw.setFocus()

    @property
    def password(self) -> str:
        return self._pw.text()

    def _accept(self) -> None:
        if not self._pw.text():
            return self._show_error("请输入主密码")
        self._clear_error()
        self.accept()

    @staticmethod
    def get(parent, path: str) -> tuple[str, bool]:
        """返回 (密码, 是否确定)。"""
        dlg = UnlockDialog(parent, path)
        return dlg.password, dlg.exec() == QDialog.DialogCode.Accepted


class ChangeMasterDialog(_BaseDialog):
    """改主密码：库内容不重加密，只重包数据密钥。"""

    def __init__(self, parent=None, has_current: bool = True) -> None:
        super().__init__(parent, "修改主密码")
        self._has_current = has_current
        self._old = _password_field("当前主密码")
        self._new = _password_field("新主密码")
        self._new2 = _password_field("再次输入确认")
        self._accept_weak = self._new_weak_override()
        self._new.textChanged.connect(lambda: self._reset_weak_override(self._accept_weak))

        note = QLabel("库内容不会重新加密，仅重新包装数据密钥，瞬间完成。")
        note.setProperty("dim", True)
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.setSpacing(theme.GAP)
        if has_current:
            form.addRow("当前", self._old)
        form.addRow("新密码", self._new)
        form.addRow("确认", self._new2)

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.GAP)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(self._accept_weak)
        layout.addWidget(self._error)
        layout.addWidget(buttons)

    @property
    def old_password(self) -> str:
        return self._old.text()

    @property
    def new_password(self) -> str:
        return self._new.text()

    def _accept(self) -> None:
        new, new2 = self._new.text(), self._new2.text()
        if self._has_current and not self._old.text():
            return self._show_error("请输入当前主密码")
        if not new:
            return self._show_error("新密码不能为空")
        if new != new2:
            return self._show_error("两次输入不一致")
        if password_strength(new) == "weak":
            if self._block_on_weak(
                self._accept_weak,
                f"新主密码偏弱，容易被暴力破解。{_MIN_MASTER_LEN_HINT}。勾选下方选项可继续。",
            ):
                return
        self._clear_error()
        self.accept()


class GeneratorDialog(_BaseDialog):
    """生成强密码，可直接填回条目。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, "生成强密码")
        self._result = QLineEdit()
        self._result.setReadOnly(True)
        self._result.setStyleSheet(f"font-family: Consolas, monospace; color: {theme.RED_DARK};")

        self._len = QSpinBox()
        self._len.setRange(8, 64)
        self._len.setValue(20)
        self._symbols = QCheckBox("含符号")
        self._symbols.setChecked(True)
        self._digits = QCheckBox("含数字")
        self._digits.setChecked(True)
        self._upper = QCheckBox("含大写")
        self._upper.setChecked(True)
        self._no_ambiguous = QCheckBox("排除易混淆字符 0O1lI|")

        regenerate = QPushButton("重新生成")
        regenerate.clicked.connect(self._regenerate)
        copy_btn = QPushButton("复制")
        copy_btn.clicked.connect(self._copy)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("使用这个密码")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("关闭")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        opts = QHBoxLayout()
        opts.setSpacing(theme.GAP)
        for w in (self._symbols, self._digits, self._upper, self._no_ambiguous):
            opts.addWidget(w)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        row.addWidget(QLabel("长度"))
        row.addWidget(self._len)
        row.addStretch(1)
        row.addWidget(regenerate)
        row.addWidget(copy_btn)

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.GAP)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.addWidget(self._result)
        layout.addLayout(row)
        layout.addLayout(opts)
        layout.addWidget(buttons)

        for w in (self._len, self._symbols, self._digits, self._upper, self._no_ambiguous):
            w.setProperty("primary", False)
        self._len.valueChanged.connect(self._regenerate)
        for cb in (self._symbols, self._digits, self._upper, self._no_ambiguous):
            cb.toggled.connect(self._regenerate)
        self._regenerate()

    def _regenerate(self) -> None:
        try:
            self._result.setText(generate(
                length=self._len.value(),
                lower=True,
                upper=self._upper.isChecked(),
                digits=self._digits.isChecked(),
                symbols=self._symbols.isChecked(),
                exclude_ambiguous=self._no_ambiguous.isChecked(),
            ))
            self._clear_error()
        except ValueError as e:
            self._show_error(str(e))

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._result.text())

    @property
    def password(self) -> str:
        return self._result.text()

    @staticmethod
    def get(parent) -> str | None:
        dlg = GeneratorDialog(parent)
        return dlg.password if dlg.exec() == QDialog.DialogCode.Accepted else None
