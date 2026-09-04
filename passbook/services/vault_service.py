"""保险库文件生命周期：创建 / 打开 / 锁定 / 保存 / 改主密码。

安全约定：
- 会话持有**明文 Vault**，但不持有主密码、不持有任何密钥。
- 每次 save(password) 由调用方（CLI/GUI）临时提供主密码派生 KEK。
- lock() 清空明文引用并触发 GC，敏感数据不可变 str 由解释器回收。
"""

import gc
import json
import os

from ..core.exceptions import PassbookError
from ..core.vault import Vault
from ..crypto.kdf import KdfParams
from ..format.reader import load
from ..format.writer import BACKUP_SUFFIXES, restore_from, save as save_file


class VaultService:
    def __init__(self, path: str) -> None:
        self.path = path
        self._vault: Vault | None = None

    # ---------- 生命周期 ----------
    def create(self, password: str, params: KdfParams | None = None) -> Vault:
        """新建一个空保险库并立即保存到磁盘。"""
        if self._vault is not None:
            raise PassbookError("已有打开的保险库，请先 lock")
        vault = Vault()
        payload = json.dumps(vault.to_dict(), ensure_ascii=False).encode("utf-8")
        save_file(self.path, password, payload, params=params)
        self._vault = vault
        return vault

    def open(self, password: str) -> Vault:
        """打开并解锁保险库，返回明文 Vault。"""
        payload = load(self.path, password)
        data = json.loads(payload.decode("utf-8"))
        self._vault = Vault.from_dict(data)
        return self._vault

    def save(self, password: str) -> None:
        """把当前明文 Vault 写回磁盘（原子写 + 备份轮转）。"""
        self._require_unlocked()
        payload = json.dumps(self._vault.to_dict(), ensure_ascii=False).encode("utf-8")
        save_file(self.path, password, payload)

    def lock(self) -> None:
        """锁定：丢弃明文 Vault 引用。"""
        self._vault = None
        gc.collect()

    def change_password(self, old_password: str, new_password: str) -> None:
        """改主密码：用新密码重新加密同一份明文，毫秒级（数据不重输）。

        改完必须清掉旧备份——它们仍用**旧主密码**加密。改主密码的常见动机
        就是"旧密码可能已泄露"，留着旧密码能解开的备份等于没改。
        """
        vault = self.open(old_password)  # 校验旧密码；失败抛 CredentialsError
        payload = json.dumps(vault.to_dict(), ensure_ascii=False).encode("utf-8")
        save_file(self.path, new_password, payload)
        self._discard_backups()
        self._vault = vault

    def _discard_backups(self) -> None:
        """删除所有轮转备份（仅改主密码后调用，见 change_password）。"""
        for suffix in BACKUP_SUFFIXES:
            p = f"{self.path}{suffix}"
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass  # 删不掉也不阻塞改密码；极端情况由用户手动处理

    # ---------- 备份 / 恢复 ----------
    def list_backups(self) -> list[str]:
        """存在的备份路径，按新→旧排序（.bak.1 最新）。"""
        return [f"{self.path}{s}" for s in BACKUP_SUFFIXES
                if os.path.exists(f"{self.path}{s}")]

    def probe_backup(self, backup_path: str, password: str) -> int | None:
        """验证备份能否用该密码完整打开，返回条目数；不可用返回 None。

        必须真正解密 + 解析一遍：文件存在不代表没坏，只看头部也发现不了
        payload 损坏——这正是要恢复的场景。
        """
        try:
            payload = load(backup_path, password)
            vault = Vault.from_dict(json.loads(payload.decode("utf-8")))
        except (PassbookError, ValueError, KeyError):
            return None
        return len(vault.entries)

    def restore_backup(self, password: str, index: int | None = None) -> str:
        """从备份恢复主库，返回实际使用的备份路径。

        index 为 None 时自动挑选：按 .bak.1 → .bak.2 顺序取第一个能用当前
        主密码完整解密的备份，坏备份自动跳过。恢复前当前主库另存为 .broken。
        """
        backups = self.list_backups()
        if not backups:
            raise PassbookError(
                f"没有找到备份文件（{self.path}.bak.1 / .bak.2）"
            )
        if index is not None:
            if index < 1 or index > len(BACKUP_SUFFIXES):
                raise PassbookError(f"备份序号须为 1 或 2，实际 {index}")
            chosen = f"{self.path}{BACKUP_SUFFIXES[index - 1]}"
            if chosen not in backups:
                raise PassbookError(f"备份不存在：{chosen}")
            if self.probe_backup(chosen, password) is None:
                raise PassbookError(f"该备份无法用当前主密码打开：{chosen}")
        else:
            chosen = next(
                (b for b in backups if self.probe_backup(b, password) is not None),
                None,
            )
            if chosen is None:
                raise PassbookError(
                    "没有一份备份能用当前主密码打开（密码错误或备份也已损坏）"
                )
        restore_from(self.path, chosen)
        return chosen

    # ---------- 访问 ----------
    @property
    def vault(self) -> Vault:
        self._require_unlocked()
        return self._vault

    @property
    def unlocked(self) -> bool:
        return self._vault is not None

    def _require_unlocked(self) -> None:
        if self._vault is None:
            raise PassbookError("保险库未解锁，请先 open")
