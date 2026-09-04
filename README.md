# 密码本 (Passbook)

> 个人倾向的轻量密码管理库——**轻到能塞进 U 盘随身带走**，
> 有较为现代、简约的图形界面，上手门槛低。

数据只在本机，无服务端、无同步、无网络请求。

- **轻量便携**：单个 exe 约 49MB，拷进 U 盘双击即用；密码库就存在 exe 旁边，不依赖任何服务
- **简约界面**：citrus 酸橙信笺风格（米白纸底 + 珊瑚橘点缀），开箱即用、无配置
- **加密可靠**：Argon2id 派生主密钥 + AES-256-GCM（AEAD），双层密钥——改主密码毫秒级完成
- **稳健存储**：单文件 `.pbk` 原子写，自动保留 2 份轮转备份，坏了能恢复
- **双形态**：图形界面日常使用；命令行做批量导入导出与备份恢复（recover）

## 形态与库位置

| 形态 | 说明 |
|---|---|
| GUI | 双击 exe 即用；也可 `python -m passbook gui`（需装 PySide6） |
| CLI | `python -m passbook <命令>`，供脚本、批量导入导出、库损坏应急（recover） |

**库文件固定放程序旁**（打包版在 exe 同目录，源码版在当前目录），名字固定 `passbook.pbk`。
程序不提供"选择保存位置"的入口——这是刻意的安全取舍：可选位置意味着可能把库放进
网盘同步目录、共享文件夹这些泄露面。命令行 `-f` 参数保留但不出现在帮助里，
仅供自动化测试与应急恢复使用。

## 安装

```bash
pip install -r requirements.txt                 # 核心（CLI）
pip install PySide6-Essentials                  # GUI 可选，约 600MB 磁盘占用
```

核心依赖：`argon2-cffi`、`cryptography`、`pyperclip`，需要 Python 3.12+。


## 快速开始

```bash
# 1. 建库（设主密码，两次确认）
python -m passbook init

# 2. 加一条
python -m passbook add --title GitHub --username xiji --url https://github.com --gen

# 3. 查看（密码默认打码，--show 显示明文，--copy 复制到剪贴板 45 秒后自动清空）
python -m passbook get GitHub --show
python -m passbook get GitHub --copy

# 4. 列表 / 搜索
python -m passbook list
python -m passbook search github
```

主密码只在需要时输入（不回显），进程退出即释放内存。

## 命令一览

| 命令 | 说明 |
|---|---|
| `init` | 创建新保险库（设主密码） |
| `add [--type login\|note\|card\|identity]` | 新增条目，`--gen` 自动生成强密码，`--folder` 归类（文件夹自动创建） |
| `list [--folder X] [--trash]` | 列出条目 / 回收站 |
| `get <id\|标题> [--show] [--copy]` | 查看条目 |
| `search <关键词> [--trash]` | 搜索（标题 / 用户名 / URL） |
| `edit <id\|标题>` | 编辑（回车保留原值） |
| `rm <id\|标题>` | 删除（进回收站，可恢复） |
| `restore <id\|标题>` | 从回收站恢复条目 |
| `purge <id\|标题>` / `purge-trash` | 彻底删除 / 清空回收站 |
| `gen [--len 20] [--no-symbols] [--copy]` | 生成强密码 |
| `folders` | 列出文件夹及条目数 |
| `export json\|csv [-o file]` | 导出（`json` 可完整还原，`csv` 为 Chrome/Edge 格式） |
| `import <file.csv\|file.json> [--folder X]` | 导入（重复条目自动跳过） |
| `passwd` | 改主密码（库内容不重加密） |
| `recover [--from 1\|2]` | **从备份恢复**（主库损坏时用） |
| `gui` | 启动图形界面（源码开发调试用；打包版双击 exe 即是 GUI） |

## 数据与备份

库文件为单文件 `.pbk`。每次保存前自动轮转备份：

```
passbook.pbk.bak.1    ← 上一次保存前的内容（较新）
passbook.pbk.bak.2    ← 再上一次（较旧）
```

**主库打不开时**（保存中途断电、文件被其他程序写坏等），会提示数据校验失败，此时恢复：

```bash
python -m passbook recover          # 自动挑第一个能打开的备份
python -m passbook recover --from 2 # 明确指定用 bak.2
```

`recover` 会先备份是否完好（真解密一遍，坏备份自动跳过），再恢复；当前坏库另存为 `passbook.pbk.broken` 保留现场，确认无误后可自行删除。

> 注意：轮转备份只保留 2 份，恢复**可能**丢失最后一次保存的内容。重要变更请用 `export json` 另行归档。

## 安全说明

- 条目所有字段（含标题、URL、备注）整体加密，不存在"只加密密码、URL 明文"的泄露
- 密码生成全部使用 `secrets`（CSPRNG），不用 `random`
- 复制密码后 45 秒自动清空剪贴板，且仅当内容未被改写时才清
- 主密码校验与 MAC 比较均为常数时间
- 错误分类：`主密码错误或被篡改` / `不是密码本文件或版本过新` / `数据损坏，请从备份恢复`
- 库文件丢失不泄密（无主密码无法解密），但**库文件损坏且无备份 = 数学意义上不可恢复**，请勿删除 `.bak.*`

## 图形界面（GUI）

界面参考 "citrus-letter 酸橙信笺" 视觉（米白纸底 `#f2ede6` + 珊瑚橘 `#ed685f`，
半透明白玻璃层控件、圆角、9px 细滚动条）。首次启动流程：

1. **创建保险库**：设主密码（两次确认，弱密码会被拒）
2. **主界面**：左侧可搜索的条目列表，右侧详情
3. 增删改查、一键生成强密码、复制密码（45 秒自动清空剪贴板）
4. **锁定**：手动锁定，或 **5 分钟无操作自动锁定**——锁定即清零内存中的主密码

**一键导出明文副本**（顶栏"导出"按钮，为将来换方案/迁移准备）：
- **JSON 完整副本**：含全部条目、文件夹、备注，密码本可无损还原
- **CSV 迁移格式**：Chrome/Edge 兼容，KeePassXC、Bitwarden、1Password 等都能导入

导出的是**明文文件**，任何人拿到都能读，保存后请妥善保管、用后即删。
右上角 "⋯" 菜单里有修改主密码；`recover` 等应急命令请用 `passbook-cli.exe`。

## 打包 exe（便携版）

```bash
py build.py            # 产出两个 exe
py build.py --gui      # 只打 GUI
py build.py --cli      # 只打 CLI
py build.py --clean    # 先清 build/ dist/ 再打
```

| 产物 | 体积 | 用途 |
|---|---|---|
| `dist/passbook.exe` | 约 49 MB | **GUI**，双击即用（PySide6 是大头） |
| `dist/passbook-cli.exe` | 约 11 MB | CLI，脚本 / 批量导入导出 / 库损坏时 `recover` |

目标机器**无需安装 Python**。拷进 U 盘任意目录双击 `passbook.exe` 即可，
库文件自动创建在 **exe 同目录** 的 `passbook.pbk`（固定位置，程序内不可改）。

注意点：

- GUI 版 `--windowed`（无控制台），CLI 版 `--console`（要 stdout/getpass），互不通用。
- 入口 `run.py`（CLI）/ `run_gui.py`（GUI），都不能直接用 `passbook/__main__.py`——
  它用相对导入，被当顶层脚本打包时 `__package__` 为空会 ImportError。
- CLI 版排除了 PySide6（`cli.py` 的 `gui` 子命令用字符串导入绕开静态分析，
  否则 PyInstaller 会把整个 Qt 塞进 11MB 的 CLI）。
- PyInstaller 不支持交叉编译：Windows exe 只能在 Windows 上打。
- `--noupx` 不加壳，缓解 Windows Defender 对 PyInstaller 单文件的偶发误报。

## 开发

```bash
pytest -q          # 155 个测试，全部使用临时目录，不落盘生产数据
```

分层约定（新增 GUI 或换框架时不动核心）：

```
core/     领域模型，纯内存，不碰加密不碰 IO
crypto/   Argon2id / AES-256-GCM / 双层密钥
format/   文件格式，只认字节不认业务语义
services/ 业务用例，CLI 与 GUI 共用
io/       导入导出
cli.py    命令行，一行加密代码都没有
```

文件格式规范见 [docs/format-spec.md](docs/format-spec.md)，完整设计见 [DESIGN.md](DESIGN.md)。
参与开发请先读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE)
