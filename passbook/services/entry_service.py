"""条目业务编排：增删改查 / 搜索 / 分类 / 软删 / 剪贴板。

Vault 提供原子操作，这里把它们组合成"一个命令一个动作"的用例，
并补充跨条目规则：标题必填、文件夹必须存在、复制密码带自动清空。
"""

import threading

from ..core.entry import ENTRY_TYPES, Entry
from ..core.exceptions import PassbookError
from ..core.vault import Vault

_CLIPBOARD_TTL = 45.0  # 默认 45 秒后自动清空剪贴板
_clipboard_timer: threading.Timer | None = None


class EntryService:
    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    @property
    def vault(self) -> Vault:
        return self._vault

    # ---------- 创建 / 更新 ----------
    def create(
        self,
        entry_type: str = "login",
        data: dict | None = None,
        folder_id: str | None = None,
        favorite: bool = False,
    ) -> Entry:
        data = dict(data or {})
        title = str(data.get("title", "")).strip()
        if not title:
            raise PassbookError("条目必须填写标题")
        if folder_id is not None and self._vault.get_folder(folder_id) is None:
            raise PassbookError(f"文件夹不存在：{folder_id}")
        entry = Entry(
            type=entry_type, data=data, folder_id=folder_id, favorite=favorite
        )
        self._vault.add_entry(entry)
        return entry

    def update(self, entry_id: str, data: dict) -> Entry:
        """部分更新：只合并传入的字段，不影响其他字段。"""
        entry = self.get(entry_id)
        merged = dict(entry.data)
        merged.update(data or {})
        if not str(merged.get("title", "")).strip():
            raise PassbookError("标题不能清空")
        entry.data = merged
        self._vault.update_entry(entry)
        return entry

    def set_folder(self, entry_id: str, folder_id: str | None) -> None:
        entry = self.get(entry_id)
        if folder_id is not None and self._vault.get_folder(folder_id) is None:
            raise PassbookError(f"文件夹不存在：{folder_id}")
        entry.folder_id = folder_id
        self._vault.update_entry(entry)

    def toggle_favorite(self, entry_id: str) -> bool:
        entry = self.get(entry_id)
        entry.favorite = not entry.favorite
        self._vault.update_entry(entry)
        return entry.favorite

    # ---------- 查询 ----------
    def get(self, entry_id: str) -> Entry:
        entry = self._vault.get_entry(entry_id)
        if entry is None:
            raise KeyError(f"条目不存在：{entry_id}")
        return entry

    def list_entries(self, folder_id: str | None = None) -> list[Entry]:
        return self._vault.list_active(folder_id)

    def list_trash(self) -> list[Entry]:
        return self._vault.list_trash()

    def search(self, query: str, include_trash: bool = False) -> list[Entry]:
        return self._vault.search(query, include_trash=include_trash)

    # ---------- 删除 / 回收站 ----------
    def delete(self, entry_id: str) -> None:
        """软删：进回收站，可恢复。"""
        self._vault.soft_delete(entry_id)

    def restore(self, entry_id: str) -> None:
        self._vault.restore(entry_id)

    def purge(self, entry_id: str) -> None:
        """从回收站彻底删除。"""
        self._vault.purge(entry_id)

    def purge_trash(self) -> int:
        return self._vault.purge_trash()

    # ---------- 剪贴板 ----------
    def copy_password(self, entry_id: str, ttl: float = _CLIPBOARD_TTL) -> None:
        """复制密码到剪贴板，ttl 秒后自动清空（内容已被改写则不动）。

        pyperclip 延迟导入：CLI 依赖它，GUI 可替换实现；测试时 mock。
        """
        entry = self.get(entry_id)
        password = str(entry.data.get("password", ""))
        if not password:
            raise PassbookError("该条目没有保存密码")
        import pyperclip  # 延迟导入，避免污染无 GUI 环境

        pyperclip.copy(password)
        schedule_clipboard_clear(ttl, password)


def schedule_clipboard_clear(ttl: float, expected: str) -> None:
    """ttl 秒后若剪贴板内容仍是 expected 则清空（用户已改写则不动）。

    模块级函数以便测试注入；重复调用会取消上一个定时器。
    """
    global _clipboard_timer
    if _clipboard_timer is not None:
        _clipboard_timer.cancel()

    def _do() -> None:
        try:
            import pyperclip
            if pyperclip.paste() == expected:
                pyperclip.copy("")
        except Exception:
            pass  # 剪贴板不可用（无图形会话）时静默，不打断主流程

    _clipboard_timer = threading.Timer(ttl, _do)
    _clipboard_timer.daemon = True
    _clipboard_timer.start()
