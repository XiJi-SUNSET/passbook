"""打包入口：以绝对导入方式启动 CLI。

不能直接把 passbook/__main__.py 交给 PyInstaller —— 它用的是相对导入
（from .cli import main），被当作顶层脚本运行时 __package__ 为空，
会抛 ImportError: attempted relative import with no known parent package。
"""

from passbook.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
