"""条目新增 / 编辑对话框。

字段沿用 Entry.data 的不透明 JSON 设计：这里只收集，
不新增明文字段，避免"只加密密码、URL 明文"那类错误。
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..core.entry import (
    ACCOUNT_KIND_LABELS,
    ACCOUNT_KIND_PLACEHOLDERS,
    ENTRY_TYPES,
    login_account_kind,
)
from . import theme
from .dialogs import GeneratorDialog, _BaseDialog

_TYPE_LABELS = {
    "login": "登录账号",
    "note": "安全笔记",
    "card": "银行卡",
    "identity": "身份信息",
}


class EntryDialog(_BaseDialog):
    """entry 为 None 时是新增，否则是编辑（预填现有值）。"""

    def __init__(self, parent=None, entry=None) -> None:
        super().__init__(parent, "编辑条目" if entry else "新增条目")
        self._entry = entry
        data = dict(entry.data) if entry else {}

        self._type = QComboBox()
        for t in ENTRY_TYPES:
            self._type.addItem(_TYPE_LABELS.get(t, t), t)
        current = entry.type if entry else "login"
        self._type.setCurrentIndex(list(ENTRY_TYPES).index(current))
        self._type.setEnabled(entry is None)  # 已有条目不允许改类型（字段语义不同）

        self._title = QLineEdit(str(data.get("title", "")))
        self._username = QLineEdit(str(data.get("username", "")))
        # 登录标识支持邮箱/手机号/用户名三种形态，标签随输入内容智能切换
        self._username.textChanged.connect(self._sync_account_label)
        self._url = QLineEdit(str(data.get("url", "")))

        self._password = QLineEdit(str(data.get("password", "")))
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("留空表示不保存密码")

        self._reveal = QPushButton("显示")
        self._reveal.setCheckable(True)
        self._reveal.toggled.connect(self._toggle_reveal)

        gen_btn = QPushButton("生成")
        gen_btn.clicked.connect(self._generate)

        pw_row = QHBoxLayout()
        pw_row.setSpacing(8)
        pw_row.addWidget(self._password, 1)
        pw_row.addWidget(self._reveal)
        pw_row.addWidget(gen_btn)

        self._notes = QPlainTextEdit(str(data.get("notes", "")))
        self._notes.setPlaceholderText("备注")
        self._notes.setFixedHeight(84)

        self._favorite = QCheckBox("标记为收藏")
        self._favorite.setChecked(bool(entry.favorite) if entry else False)

        self._login_rows: list[tuple[str, object]] = []
        self._form = QFormLayout()
        self._form.setSpacing(theme.GAP)
        self._form.addRow("类型", self._type)
        self._form.addRow("标题", self._title)
        self._form.addRow("账号", self._username)
        self._form.addRow("密码", pw_row)
        self._form.addRow("链接", self._url)
        self._login_rows = [(self._form.labelForField(self._username), self._username),
                            (self._form.labelForField(pw_row), pw_row),
                            (self._form.labelForField(self._url), self._url)]
        self._sync_account_label()  # 按现有值（编辑场景）更新标签与占位

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.GAP)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.addLayout(self._form)
        layout.addWidget(QLabel("备注"))
        layout.addWidget(self._notes)
        layout.addWidget(self._favorite)
        layout.addWidget(self._error)
        layout.addWidget(buttons)

        self._type.currentIndexChanged.connect(self._sync_visible_rows)
        self._sync_visible_rows()
        self._title.setFocus()

    # ---------- 交互 ----------
    def _toggle_reveal(self, on: bool) -> None:
        self._reveal.setText("隐藏" if on else "显示")
        self._password.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        )

    def _sync_account_label(self) -> None:
        """登录账号标签随输入智能切换：含 @ → 邮箱，11 位手机号 → 手机号，其余 → 用户名。"""
        kind = login_account_kind(self._username.text())
        label = self._form.labelForField(self._username)
        if label is not None:
            label.setText(ACCOUNT_KIND_LABELS[kind])
        self._username.setPlaceholderText(ACCOUNT_KIND_PLACEHOLDERS[kind])

    def _generate(self) -> None:
        pw = GeneratorDialog.get(self)
        if pw:
            self._password.setText(pw)
            self._reveal.setChecked(True)

    def _sync_visible_rows(self) -> None:
        """只有 login 才有用户名/密码/链接；其他类型只留标题与备注。"""
        is_login = self._type.currentData() == "login"
        for label, field in self._login_rows:
            if label is not None:
                label.setVisible(is_login)
            if isinstance(field, QLineEdit):
                field.setVisible(is_login)
            else:  # QHBoxLayout 容器
                for i in range(field.count()):
                    item = field.itemAt(i)
                    if item and item.widget():
                        item.widget().setVisible(is_login)

    # ---------- 结果 ----------
    def entry_type(self) -> str:
        return self._type.currentData()

    def favorite(self) -> bool:
        return self._favorite.isChecked()

    def data(self) -> dict:
        """返回欲写入 Entry.data 的字段（只含该类型用得到的）。"""
        out = {"title": self._title.text().strip()}
        if self.entry_type() == "login":
            out["username"] = self._username.text()
            out["password"] = self._password.text()
            out["url"] = self._url.text()
        notes = self._notes.toPlainText()
        if notes:
            out["notes"] = notes
        return out

    def _accept(self) -> None:
        if not self._title.text().strip():
            return self._show_error("标题不能为空")
        self._clear_error()
        self.accept()
