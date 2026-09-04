"""GUI 打包入口：产出双击即用的 passbook.exe。

GUI 版无控制台（--windowed），必须走绝对导入 + 独立入口，
不能复用 run.py（那是 CLI 用的）。
"""

from passbook.ui.app import run_gui

if __name__ == "__main__":
    raise SystemExit(run_gui())
