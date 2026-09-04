"""库文件路径：固定放程序旁，用户不能选位置。

为什么不给用户选：
- 便携场景（U 盘/移动硬盘）下，exe 与 .pbk 必须同进同退，分开存放只会丢数据
- 可选路径意味着可能把库放进网盘同步目录、共享文件夹、临时目录——都是泄露面
- 少一个参数就少一处要维护、要测试、要出错的地方

打包后（sys.frozen）：exe 所在目录
开发/源码运行：当前工作目录

测试若要指定别处，用 -f 隐藏参数或直接构造 VaultService(path)。
"""

import os
import sys

VAULT_FILENAME = "passbook.pbk"


def vault_dir() -> str:
    """库文件所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


def vault_path() -> str:
    """默认库文件完整路径。"""
    return os.path.join(vault_dir(), VAULT_FILENAME)
