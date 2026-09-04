"""UI 会话：解锁状态、主密码缓存、内存清零、自动锁定。

与 CLI 不同，GUI 一次解锁后要连续操作，不可能每条命令都重输主密码，
所以会话内必须缓存主密码。缓存就带来两件事必须做对：

1. **能清零**：主密码存 bytearray 而不是 str —— str 不可变，
   锁定时没法覆写，只能等 GC，副本在内存里躺到进程结束。
2. **会自动失效**：无操作超时自动锁定，不能让解锁状态一直挂着。

局限（诚实记录）：bytearray 只解决了"缓存的那一份"。真正要用时
仍要转成 str 交给 VaultService，这份临时 str 逃不掉，生命周期很短但存在。
Python 里彻底清零敏感数据需要全链路改成 bytearray（含序列化/搜索/导出），
改动面与收益不匹配，暂不做——见 DESIGN.md 的已知取舍。
"""

import os

from ..core.exceptions import PassbookError
from ..core.vault import Vault
from ..crypto.kdf import KdfParams
from ..services.entry_service import EntryService
from ..services.vault_service import VaultService

AUTO_LOCK_SECONDS = 300  # 5 分钟无操作自动锁定


class Session:
    """一个解锁中的保险库会话。不持有任何密钥，只持有主密码与明文库。"""

    def __init__(self, path: str, params: KdfParams | None = None) -> None:
        self.path = path
        self.service = VaultService(path)
        self._params = params
        self._password: bytearray | None = None

    # ---------- 状态 ----------
    @property
    def unlocked(self) -> bool:
        return self._password is not None and self.service.unlocked

    @property
    def vault(self) -> Vault:
        return self.service.vault

    @property
    def entries(self) -> EntryService:
        """条目服务（轻量对象，随取随用）。"""
        return EntryService(self.service.vault)

    def vault_exists(self) -> bool:
        return os.path.exists(self.path)

    # ---------- 生命周期 ----------
    def create(self, password: str) -> None:
        """建库并记住主密码。"""
        self.service.create(password, params=self._params)
        self._remember(password)

    def unlock(self, password: str) -> None:
        """解锁；密码错误时抛出，不记住任何东西。"""
        self.service.open(password)
        self._remember(password)

    def save(self) -> None:
        """保存改动（用会话内缓存的主密码，不再打扰用户）。"""
        self.service.save(self._password_text())

    def change_password(self, new_password: str) -> None:
        """改主密码；旧密码立即清零，缓存换成新的。"""
        self.service.change_password(self._password_text(), new_password)
        self._wipe()
        self._remember(new_password)

    def lock(self) -> None:
        """锁定：清零主密码缓存并丢弃明文库。"""
        self._wipe()
        self.service.lock()

    # ---------- 内部 ----------
    def _remember(self, password: str) -> None:
        self._wipe()  # 先清旧的，避免叠加
        self._password = bytearray(password.encode("utf-8"))

    def _password_text(self) -> str:
        if self._password is None:
            raise PassbookError("会话未解锁")
        return bytes(self._password).decode("utf-8")

    def _wipe(self) -> None:
        """逐字节覆写清零后丢弃引用。"""
        if self._password is not None:
            for i in range(len(self._password)):
                self._password[i] = 0
            self._password = None
