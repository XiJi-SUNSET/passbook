"""保险库模型：条目容器 + 文件夹分类 + CRUD/搜索/软删。

纯内存领域对象：不碰 IO、不碰加密。持久化交给 format 层，
业务规则（搜索、软删、回收站）都在这里，CLI 与将来的 GUI 共用。
"""

from dataclasses import dataclass, field

from .entry import Entry, new_id, now_iso

FORMAT_VERSION = 1


@dataclass
class Folder:
    name: str = ""
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, d: dict) -> "Folder":
        return cls(id=d["id"], name=d.get("name", ""), created_at=d["created_at"])


@dataclass
class Vault:
    folders: list[Folder] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def touch(self) -> None:
        self.updated_at = now_iso()

    # ---------- 条目 CRUD ----------
    def add_entry(self, entry: Entry) -> Entry:
        if self.get_entry(entry.id) is not None:
            raise ValueError(f"条目 id 已存在：{entry.id}")
        self.entries.append(entry)
        self.touch()
        return entry

    def get_entry(self, entry_id: str) -> Entry | None:
        return next((e for e in self.entries if e.id == entry_id), None)

    def update_entry(self, entry: Entry) -> None:
        target = self.get_entry(entry.id)
        if target is None:
            raise KeyError(f"条目不存在：{entry.id}")
        idx = self.entries.index(target)
        self.entries[idx] = entry
        entry.touch()
        self.touch()

    def soft_delete(self, entry_id: str) -> None:
        """删除 = 打 deleted_at 时间戳（进回收站），可恢复。"""
        e = self.get_entry(entry_id)
        if e is None:
            raise KeyError(f"条目不存在：{entry_id}")
        e.deleted_at = now_iso()
        e.touch()
        self.touch()

    def restore(self, entry_id: str) -> None:
        e = self.get_entry(entry_id)
        if e is None:
            raise KeyError(f"条目不存在：{entry_id}")
        e.deleted_at = None
        e.touch()
        self.touch()

    def purge(self, entry_id: str) -> None:
        """从回收站彻底删除（物理移除）。"""
        e = self.get_entry(entry_id)
        if e is None:
            raise KeyError(f"条目不存在：{entry_id}")
        self.entries.remove(e)
        self.touch()

    def purge_trash(self) -> int:
        """清空回收站，返回清除数量。"""
        trash = [e for e in self.entries if e.deleted_at is not None]
        for e in trash:
            self.entries.remove(e)
        if trash:
            self.touch()
        return len(trash)

    # ---------- 查询 ----------
    def list_active(self, folder_id: str | None = None) -> list[Entry]:
        out = [e for e in self.entries if e.deleted_at is None]
        if folder_id is not None:
            out = [e for e in out if e.folder_id == folder_id]
        return out

    def list_trash(self) -> list[Entry]:
        return [e for e in self.entries if e.deleted_at is not None]

    def search(self, query: str, include_trash: bool = False) -> list[Entry]:
        """标题/用户名/URL 模糊匹配（大小写不敏感）。"""
        q = query.strip().lower()
        if not q:
            return []
        out = []
        for e in self.entries:
            if e.deleted_at is not None and not include_trash:
                continue
            hay = " ".join(
                str(e.data.get(k, "")) for k in ("title", "username", "url")
            ).lower()
            if q in hay:
                out.append(e)
        return out

    # ---------- 文件夹 ----------
    def add_folder(self, name: str) -> Folder:
        name = name.strip()
        if not name:
            raise ValueError("文件夹名不能为空")
        folder = Folder(name=name)
        self.folders.append(folder)
        self.touch()
        return folder

    def rename_folder(self, folder_id: str, name: str) -> None:
        f = self.get_folder(folder_id)
        if f is None:
            raise KeyError(f"文件夹不存在：{folder_id}")
        name = name.strip()
        if not name:
            raise ValueError("文件夹名不能为空")
        f.name = name
        self.touch()

    def delete_folder(self, folder_id: str) -> None:
        """删文件夹时条目回退到"未分类"（folder_id=None），不删条目。"""
        f = self.get_folder(folder_id)
        if f is None:
            raise KeyError(f"文件夹不存在：{folder_id}")
        self.folders.remove(f)
        for e in self.entries:
            if e.folder_id == folder_id:
                e.folder_id = None
                e.touch()
        self.touch()

    def get_folder(self, folder_id: str) -> Folder | None:
        return next((f for f in self.folders if f.id == folder_id), None)

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        return {
            "format_version": FORMAT_VERSION,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "folders": [f.to_dict() for f in self.folders],
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Vault":
        v = cls(
            folders=[Folder.from_dict(f) for f in d.get("folders", [])],
            entries=[Entry.from_dict(e) for e in d.get("entries", [])],
            created_at=d.get("created_at", now_iso()),
            updated_at=d.get("updated_at", now_iso()),
        )
        # 只认自己支持的版本；过新版本拒绝加载，防止静默丢字段
        if d.get("format_version", FORMAT_VERSION) > FORMAT_VERSION:
            raise ValueError(f"保险库版本过新：{d.get('format_version')}")
        return v
