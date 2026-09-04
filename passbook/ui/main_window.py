"""主窗口：顶栏 + 左侧条目列表 + 右侧详情。

布局沿用参考项目的骨架——顶部 56px 工具条、下面左右分栏、细线分隔。
库文件位置固定，界面里不提供任何"换库/选路径"的入口。
"""

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.entry import ACCOUNT_KIND_LABELS, Entry, login_account_kind
from ..core.exceptions import PassbookError
from ..io.exporter import export_csv, export_json
from ..services.generator import generate
from . import theme
from .dialogs import ChangeMasterDialog, GeneratorDialog
from .entry_dialog import EntryDialog
from .session import AUTO_LOCK_SECONDS, Session

COPY_CLEAR_MS = 45_000  # 复制后 45 秒自动清空剪贴板（与 CLI 一致）

_TYPE_LABELS = {"login": "登录", "note": "笔记", "card": "银行卡", "identity": "身份"}


class MainWindow(QMainWindow):
    """解锁后的主界面。locked 信号交给 app 决定是重新解锁还是退出。"""

    locked = Signal()

    def __init__(self, session: Session) -> None:
        super().__init__()
        self._session = session
        self._current: Entry | None = None
        self._copied: str | None = None

        self.setWindowTitle("密码本")
        self.resize(880, 560)
        self.setStyleSheet(theme.stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._separator())
        root.addLayout(self._build_body(), 1)
        root.addWidget(self._separator())
        root.addWidget(self._build_status())

        self._setup_auto_lock()
        self.refresh()

    # ---------- 构建 ----------
    def _separator(self) -> QFrame:
        line = QFrame()
        line.setProperty("sep", True)
        line.setFixedHeight(1)
        return line

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(theme.HEADER_H)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(theme.PAD_X, 0, theme.PAD_X, 0)
        layout.setSpacing(theme.GAP)

        brand = QLabel("密码本")
        brand.setProperty("brand", True)

        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索标题 / 用户名 / 链接")
        self._search.setMaximumWidth(320)
        self._search.textChanged.connect(self.refresh)

        add = QPushButton("+ 新增")
        add.setProperty("primary", True)
        add.clicked.connect(self._add)

        gen = QPushButton("生成密码")
        gen.clicked.connect(self._generate)

        export_btn = QPushButton("导出")
        export_btn.clicked.connect(self._export)

        tools = QPushButton("⋯")
        tools.setProperty("icon", True)
        tools.clicked.connect(self._show_tools_menu)

        lock = QPushButton("锁定")
        lock.clicked.connect(self._lock)

        layout.addWidget(brand)
        layout.addStretch(1)
        layout.addWidget(self._search)
        layout.addWidget(add)
        layout.addWidget(gen)
        layout.addWidget(export_btn)
        layout.addWidget(tools)
        layout.addWidget(lock)
        return bar

    def _build_body(self) -> QHBoxLayout:
        body = QHBoxLayout()
        body.setContentsMargins(theme.PAD_X, theme.GAP, theme.PAD_X, theme.GAP)
        body.setSpacing(theme.GAP)

        self._list = QListWidget()
        self._list.setFixedWidth(300)
        self._list.currentItemChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(lambda _: self._edit())

        self._detail = QWidget()
        detail_layout = QVBoxLayout(self._detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(theme.GAP)

        self._detail_title = QLabel("未选择条目")
        self._detail_title.setProperty("brand", True)
        self._detail_meta = QLabel("")
        self._detail_meta.setProperty("dim", True)

        self._rows: dict[str, QLabel] = {}
        self._row_labels: dict[str, QLabel] = {}
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(8)
        for key in ("username", "password", "url"):
            self._rows[key] = self._build_row(key)
        self._notes_label = QLabel("")
        self._notes_label.setWordWrap(True)
        self._notes_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self._reveal_btn = QPushButton("显示密码")
        self._reveal_btn.setCheckable(True)
        self._reveal_btn.toggled.connect(self._render_password)
        self._reveal_btn.hide()

        actions = QHBoxLayout()
        actions.setSpacing(theme.GAP)
        self._copy_btn = QPushButton("复制密码")
        self._copy_btn.setProperty("primary", True)
        self._copy_btn.clicked.connect(self._copy_password)
        edit_btn = QPushButton("编辑")
        edit_btn.clicked.connect(self._edit)
        del_btn = QPushButton("删除")
        del_btn.setProperty("danger", True)
        del_btn.clicked.connect(self._delete)
        for w in (self._copy_btn, self._reveal_btn, edit_btn, del_btn):
            actions.addWidget(w)
        actions.addStretch(1)

        detail_layout.addWidget(self._detail_title)
        detail_layout.addWidget(self._detail_meta)
        detail_layout.addSpacing(6)
        detail_layout.addLayout(self._rows_layout)
        detail_layout.addWidget(QLabel("备注"))
        detail_layout.addWidget(self._notes_label, 1)
        detail_layout.addLayout(actions)

        body.addWidget(self._list)
        body.addWidget(self._detail, 1)
        return body

    def _build_row(self, key: str) -> QLabel:
        from PySide6.QtWidgets import QHBoxLayout as Row

        row = Row()
        row.setSpacing(8)
        label = QLabel({"username": "账号", "password": "密码", "url": "链接"}[key])
        label.setProperty("dim", True)
        label.setFixedWidth(60)
        self._row_labels[key] = label
        value = QLabel("")
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(label)
        row.addWidget(value, 1)
        container = QWidget()
        container.setLayout(row)
        self._rows_layout.addWidget(container)
        return value

    def _build_status(self) -> QWidget:
        from PySide6.QtWidgets import QHBoxLayout as Row

        bar = QWidget()
        bar.setFixedHeight(30)
        layout = Row(bar)
        layout.setContentsMargins(theme.PAD_X, 0, theme.PAD_X, 0)
        self._count = QLabel("")
        self._count.setProperty("count", True)
        hint = QLabel(f"{AUTO_LOCK_SECONDS // 60} 分钟无操作自动锁定")
        hint.setProperty("count", True)
        layout.addWidget(self._count)
        layout.addStretch(1)
        layout.addWidget(hint)
        return bar

    # ---------- 列表与详情 ----------
    def refresh(self) -> None:
        """按搜索词重建列表。"""
        query = self._search.text().strip()
        entries = (self._session.entries.search(query) if query
                   else self._session.entries.list_entries())
        self._list.clear()
        for e in entries:
            item = QListWidgetItem(self._list)
            item.setData(Qt.ItemDataRole.UserRole, e.id)
            widget = self._item_widget(e)
            item.setSizeHint(widget.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)
        self._count.setText(f"共 {len(entries)} 条")
        if not entries:
            self._clear_detail()

    def _item_widget(self, entry: Entry) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(2)
        title = QLabel(entry.title or "（无标题）")
        title.setStyleSheet(f"color: {theme.INK}; font-weight: 600;")
        sub = entry.data.get("username") or _TYPE_LABELS.get(entry.type, entry.type)
        subtitle = QLabel(f"{'★ ' if entry.favorite else ''}{sub}")
        subtitle.setStyleSheet(f"color: {theme.INK_DIM}; font-size: 11px;")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return w

    def _on_selection_changed(self, current, _previous) -> None:
        if current is None:
            return self._clear_detail()
        entry = self._session.vault.get_entry(current.data(Qt.ItemDataRole.UserRole))
        self._show_detail(entry)

    def _clear_detail(self) -> None:
        self._current = None
        self._detail_title.setText("未选择条目")
        self._detail_meta.setText("")
        for row in self._rows.values():
            row.setText("")
            row.parent().hide()
        self._notes_label.setText("")
        self._reveal_btn.hide()
        self._reveal_btn.setChecked(False)
        self._copy_btn.setEnabled(False)

    def _show_detail(self, entry: Entry | None) -> None:
        if entry is None:
            return self._clear_detail()
        self._current = entry
        self._reveal_btn.setChecked(False)
        self._detail_title.setText(entry.title or "（无标题）")
        self._detail_meta.setText(
            f"{_TYPE_LABELS.get(entry.type, entry.type)}  ·  {entry.id[:8]}"
        )
        for key in ("username", "url"):
            value = str(entry.data.get(key, ""))
            self._rows[key].setText(value)
            self._rows[key].parent().setVisible(bool(value))
        # 账号行标签按内容切换：邮箱 / 手机号 / 用户名
        if entry.data.get("username"):
            kind = login_account_kind(str(entry.data["username"]))
            self._row_labels["username"].setText(ACCOUNT_KIND_LABELS[kind])
        has_pw = bool(entry.data.get("password"))
        self._rows["password"].parent().setVisible(has_pw)
        self._reveal_btn.setVisible(has_pw)
        self._copy_btn.setEnabled(has_pw)
        self._render_password()
        self._notes_label.setText(str(entry.data.get("notes", "")))

    def _render_password(self) -> None:
        """按"显示密码"按钮状态重绘密码行。"""
        if self._current is None:
            return
        show = self._reveal_btn.isChecked()
        pw = str(self._current.data.get("password", ""))
        shown = pw if show else ("●" * min(len(pw), 12) if pw else "")
        self._rows["password"].setText(shown)
        self._reveal_btn.setText("隐藏密码" if show else "显示密码")

    # ---------- 动作 ----------
    def _add(self) -> None:
        dlg = EntryDialog(self)
        if dlg.exec() != EntryDialog.DialogCode.Accepted:
            return
        try:
            self._session.entries.create(
                entry_type=dlg.entry_type(), data=dlg.data(), favorite=dlg.favorite()
            )
            self._session.save()
        except (PassbookError, ValueError) as e:
            return self._warn(str(e))
        self.refresh()

    def _edit(self) -> None:
        if self._current is None:
            return
        dlg = EntryDialog(self, self._current)
        if dlg.exec() != EntryDialog.DialogCode.Accepted:
            return
        try:
            self._session.entries.update(self._current.id, dlg.data())
            self._current.favorite = dlg.favorite()
            self._session.save()
        except (PassbookError, ValueError) as e:
            return self._warn(str(e))
        self.refresh()

    def _delete(self) -> None:
        if self._current is None:
            return
        title = self._current.title
        if QMessageBox.question(
            self, "删除条目", f"确定删除「{title}」？\n删除后会进入回收站，可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._session.entries.delete(self._current.id)
        self._session.save()
        self.refresh()

    def _copy_password(self) -> None:
        if self._current is None:
            return
        pw = str(self._current.data.get("password", ""))
        if not pw:
            return
        QApplication.clipboard().setText(pw)
        self._copied = pw
        self._count.setText("已复制密码，45 秒后自动清空")
        QTimer.singleShot(COPY_CLEAR_MS, self._clear_clipboard)

    def _clear_clipboard(self) -> None:
        """仅当剪贴板内容仍是刚才复制的密码时才清，避免误清用户别处复制的内容。"""
        if self._copied and QApplication.clipboard().text() == self._copied:
            QApplication.clipboard().clear()
        self._copied = None
        self.refresh()

    def _generate(self) -> None:
        pw = GeneratorDialog.get(self)
        if pw:
            QApplication.clipboard().setText(pw)
            self._count.setText("已生成并复制密码（45 秒后自动清空）")

    def _change_master(self) -> None:
        dlg = ChangeMasterDialog(self, has_current=True)
        if dlg.exec() != ChangeMasterDialog.DialogCode.Accepted:
            return
        try:
            self._session.change_password(dlg.new_password)
        except PassbookError as e:
            return self._warn(str(e))
        QMessageBox.information(self, "完成", "主密码已更改（库内容未重新加密）")

    def _export(self) -> None:
        """一键导出明文副本：JSON 无损完整副本，或 CSV 迁移格式。

        文件是明文，专门方便将来换方案/迁移/人工查看用。
        """
        from PySide6.QtWidgets import QFileDialog, QInputDialog

        json_opt = "JSON 完整副本（密码本可还原，含文件夹/备注/全部类型）"
        csv_opt = "CSV 迁移格式（浏览器及 KeePass/Bitwarden 等通用）"
        choice, ok = QInputDialog.getItem(
            self, "导出明文副本",
            "文件内容为明文，请保存在安全的地方，用后及时删除：",
            [json_opt, csv_opt], 0, False,
        )
        if not ok:
            return
        if choice == csv_opt:
            text = export_csv(self._session.vault)
            default, name_filter = "passbook-export.csv", "CSV 文件 (*.csv)"
        else:
            text = export_json(self._session.vault)
            default, name_filter = "passbook-backup.json", "JSON 文件 (*.json)"
        path, _ = QFileDialog.getSaveFileName(self, "导出明文副本", default, name_filter)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        except OSError as e:
            return self._warn(f"导出失败：{e}")
        QMessageBox.information(
            self, "完成",
            f"已导出 {len(text)} 字符到\n{path}\n\n"
            "这是明文文件，任何人拿到都能直接读取——用完后请删除或妥善保管。",
        )

    def _show_tools_menu(self) -> None:
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction(QAction("修改主密码", self, triggered=self._change_master))
        menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def _warn(self, text: str) -> None:
        QMessageBox.warning(self, "出错了", text)

    # ---------- 锁定 ----------
    def _setup_auto_lock(self) -> None:
        self._lock_timer = QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._lock)
        self._lock_timer.start(AUTO_LOCK_SECONDS * 1000)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        """任何键鼠活动都推迟自动锁定。"""
        if event.type() in (
            QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove
        ):
            self._lock_timer.start(AUTO_LOCK_SECONDS * 1000)
        return super().eventFilter(obj, event)

    def _lock(self) -> None:
        self._clear_clipboard()
        self._session.lock()
        self.locked.emit()

    def closeEvent(self, event) -> None:
        self._clear_clipboard()
        self._session.lock()
        super().closeEvent(event)
