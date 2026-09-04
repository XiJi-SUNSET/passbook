"""打包脚本：产出 dist/ 下两个单文件 exe，目标机器无需安装 Python。

    py build.py            # 打全部：GUI + CLI
    py build.py --cli      # 只打 CLI
    py build.py --gui      # 只打 GUI
    py build.py --clean    # 先清 build/ dist/ 再打

产物（U 盘便携：把 GUI 那个拷走即可，库文件自动落在 exe 同目录）：

    passbook.exe        GUI（--windowed，双击即用，约 55 MB，PySide6 是大头）
    passbook-cli.exe    CLI（--console，约 11 MB，脚本/应急用：recover 等）

公共参数：
- --onefile：单文件，可单独拷进 U 盘
- --noupx：不加壳，缓解 Windows Defender 对 PyInstaller 的误报
- --hidden-import pyperclip：pyperclip 是函数内延迟导入，静态分析有概率漏
- --exclude-module pytest/PIL：只影响开发环境，不打进产物

GUI 必须 --windowed（无控制台）：它是窗口程序，不需要也不该有黑框；
CLI 必须 --console：要靠 stdout/getpass 交互，GUI 那个产物是没法当 CLI 用的。

限制：PyInstaller 不支持交叉编译，Windows exe 只能在 Windows 上打。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMON = [
    sys.executable, "-m", "PyInstaller",
    "--onefile", "--noupx", "--noconfirm",
    "--paths", str(ROOT),
    "--hidden-import", "pyperclip",
    "--exclude-module", "pytest",
    "--exclude-module", "PIL",
]

TARGETS = {
    "gui": {
        "name": "passbook",
        "entry": ROOT / "run_gui.py",
        "console": False,   # --windowed
        "exclude": [],      # GUI 版要带 Qt
    },
    "cli": {
        "name": "passbook-cli",
        "entry": ROOT / "run.py",
        "console": True,
        # cli.py 的 gui 子命令已用字符串导入绕开静态分析；这里再硬排除一层
        "exclude": ["PySide6", "shiboken6"],
    },
}


def _build_one(key: str) -> int:
    spec = TARGETS[key]
    cmd = list(COMMON)
    cmd += ["--name", spec["name"]]
    cmd += [] if spec["console"] else ["--windowed"]
    for mod in spec["exclude"]:
        cmd += ["--exclude-module", mod]
    cmd.append(str(spec["entry"]))
    print(f"\n===== 打包 {spec['name']}.exe（{'GUI' if not spec['console'] else 'CLI'}）=====")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"\n{spec['name']} 打包失败", file=sys.stderr)
        return result.returncode
    exe = ROOT / "dist" / f"{spec['name']}.exe"
    if exe.exists():
        print(f"完成：{exe}  ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


def _clean() -> None:
    """清 build/ 与 dist/ 里的旧 exe，但**绝不碰用户数据**。

    2026-09-04 事故教训：之前 rmtree(dist) 把用户放在 exe 旁的 passbook.pbk
    （及其备份）一起删了。dist 是便携设计里库文件的默认位置，
    --clean 只能删构建产物。
    """
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    dist = ROOT / "dist"
    if dist.exists():
        for f in dist.iterdir():
            if f.is_file() and f.suffix.lower() in (".exe", ".spec"):
                f.unlink(missing_ok=True)
    kept = sorted(p.name for p in dist.iterdir()) if dist.exists() else []
    data_files = [n for n in kept if not n.lower().endswith((".exe", ".spec"))]
    if data_files:
        print("注意：dist/ 中以下文件被保留（可能是你的库文件/导出文件）：")
        for n in data_files:
            print("  ", n)


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 passbook（GUI + CLI）")
    parser.add_argument("--gui", action="store_true", help="只打 GUI")
    parser.add_argument("--cli", action="store_true", help="只打 CLI")
    parser.add_argument("--clean", action="store_true", help="清构建缓存与旧 exe")
    args = parser.parse_args()

    if args.clean:
        _clean()

    wanted = []
    if args.gui and not args.cli:
        wanted = ["gui"]
    elif args.cli and not args.gui:
        wanted = ["cli"]
    else:
        wanted = ["gui", "cli"]

    for key in wanted:
        rc = _build_one(key)
        if rc:
            return rc
    print("\n全部完成。便携用法：dist/passbook.exe 拷到任意目录双击即用，"
          "库文件自动创建在同目录 passbook.pbk；数据恢复等用 dist/passbook-cli.exe。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
