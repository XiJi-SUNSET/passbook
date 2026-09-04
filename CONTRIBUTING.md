# 贡献指南

## 开发约定

**分层铁律**（学 KeePassXC，改功能前先确认自己该动哪一层）：

| 层 | 能做什么 | 不能做什么 |
|---|---|---|
| `core/` | 领域模型、业务规则 | 碰加密、碰 IO |
| `crypto/` | 算法封装 | 认业务语义 |
| `format/` | 字节的序列化 / 反序列化 | 认业务语义 |
| `services/` | 用例编排 | 直接读 stdin、直接 print |
| `io/` | 导入导出格式转换 | 改领域模型 |
| `cli.py` | 解析参数、打印、读密码 | **写哪怕一行加密代码** |
| `ui/` | 窗口、控件、交互（PySide6） | 碰 crypto / format / io 与业务规则 |

改 GUI 只动 `ui/`；改命令只动 `cli.py`；核心四层永远不动框架。

## 流程

1. **先写测试**。本项目按 TDD 推进，每个阶段以"单测全过"为验收。
   测试全部使用 `tmp_path`，不落盘生产数据。
2. 跑全量测试：`pytest -q`。
3. 涉及文件格式或密钥结构的改动，同步更新 `docs/format-spec.md`。

## 几条不能破的规矩

- 随机性只用 `secrets` / `os.urandom`，**绝不用 `random`**。
- 新增敏感字段一律进 `Entry.data` 一起加密，不要新增"明文字段"——
  否则就是经典的"只加密了密码、URL 明文泄露"。
- 写盘一律走 `format/writer.py` 的原子写，不要直接 `open(path, "w")` 覆盖库文件。
- 异常按语义分类（`CredentialsError` / `FormatError` / `PayloadChecksumError`），
  不要图省事抛裸 `Exception`。

## 打包

```bash
py build.py            # 产出两个 exe
py build.py --gui      # 只打 GUI（passbook.exe，--windowed）
py build.py --cli      # 只打 CLI（passbook-cli.exe，--console）
py build.py --clean    # 先清 build/ dist/ 再打
```

- GUI 版 `--windowed`（窗口程序无控制台），CLI 版 `--console`（靠 stdout/getpass），互不通用。
- 改打包参数去 `build.py`；新增文件确认没被 PyInstaller 漏掉（Qt 隐藏依赖靠
  `--hidden-import pyperclip`；CLI 版必须排除 PySide6，否则体积 11MB → 49MB）。
- PyInstaller 不支持交叉编译：Windows exe 只能在 Windows 上打。
