"""条目业务编排：增删改查 / 搜索 / 分类 / 软删。

Vault 提供原子操作，这里把它们组合成"一个命令一个动作"的用例，
并补充跨条目规则：标题必填、文件夹必须存在。

剪贴板不在这里：CLI 的清空时机由用户回车决定（见 cli._copy_password_interactive），
GUI 由 QTimer 驱动；两边的进程/事件循环模型不同，无法共用一套定时器。
"""

from ..core.entry import ENTRY_TYPES, Entry
from ..core.exceptions import PassbookError
from ..core.vault import Vault


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

    def update(
        self, entry_id: str, data: dict, favorite: bool | None = None
    ) -> Entry:
        """部分更新：只合并传入的字段，不影响其他字段。

        favorite 为 None 时保持原值；给出时一并更新并触发 updated_at
        （避免调用方绕过 update_entry 直接改对象导致时间戳不更新）。
        """
        entry = self.get(entry_id)
        merged = dict(entry.data)
        merged.update(data or {})
        if not str(merged.get("title", "")).strip():
            raise PassbookError("标题不能清空")
        entry.data = merged
        if favorite is not None:
            entry.favorite = favorite
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
