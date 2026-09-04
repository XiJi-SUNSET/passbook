# 密码本 (Passbook) — 项目设计方案

> v0.1 设计稿 | 2026-09-02
> 定位：纯本地离线密码管理器，Python 实现，标准版功能范围

---

## 1. 决策摘要

| 决策点 | 选择 | 理由 |
|---|---|---|
| 定位 | 纯本地离线 | 无服务端、无同步，数据只在本机，攻击面最小 |
| 技术栈 | Python 3.12+ | 本地环境已有，开发快 |
| 界面 | CLI + GUI(PySide6) 双形态 | 2026-09-04 GUI 完成：PySide6 而非原定的 tkinter（用户选了视觉优先；tkinter 自绘圆角/毛玻璃代价大于它省下的 40MB 体积）；核心/服务两层 CLI 与 GUI 共用 |
| 加密 | Argon2id + AES-256-GCM (AEAD) | 业界 2026 主流组合，GCM 自带认证，比 CBC+HMAC 少一个出错点 |
| 密钥结构 | 双层密钥 KEK → DEK | 改主密码只重包 DEK（毫秒级），不用重加密整个库 |
| 条目模型 | type + 不透明加密 JSON blob | 抄 Bitwarden Cipher 设计，加"银行卡/SSH 密钥"等新类型不改 schema |
| 存储 | 单文件 `.pbk`，原子写 + 自动轮转备份 | 密码库写坏无备份 = 数学意义上不可恢复 |
| 文件格式 | 自建格式（明文头 + GCM 认证） | 参考 KDBX 简化，KDF 参数明文入头保证可迁移 |

## 2. 目录结构

```
密码本/
├── DESIGN.md                 # 本设计文档
├── README.md                 # 使用说明
├── CONTRIBUTING.md           # 开发约定（分层铁律 / 安全红线 / 打包）
├── LICENSE                   # MIT
├── pyproject.toml            # 项目元数据 + pytest 配置
├── requirements.txt          # argon2-cffi, cryptography, pyperclip（pip 直接装用这个）
├── run.py                    # CLI 打包入口（绝对导入，绕开 __main__.py 相对导入问题）
├── run_gui.py                # GUI 打包入口
├── build.py                  # 打包脚本：产出 passbook.exe(GUI) + passbook-cli.exe(CLI)
├── .gitignore
├── .github/
│   └── workflows/ci.yml      # 跨系统跑测试 + Windows 打包验证
├── passbook/                 # 主包
│   ├── __init__.py
│   ├── __main__.py           # python -m passbook 入口
│   ├── cli.py                # CLI 层：argparse，零加密逻辑
│   ├── paths.py              # 库文件路径：固定放程序旁（用户不能选）
│   ├── core/                 # 领域模型（纯内存，无 IO 无加密）
│   │   ├── vault.py          # Vault：元数据 + 条目容器
│   │   ├── entry.py          # Entry：type + 字段字典
│   │   └── exceptions.py     # 异常体系（凭据/头校验/内容校验）
│   ├── crypto/               # 算法封装
│   │   ├── kdf.py            # Argon2id 派生 KEK
│   │   ├── cipher.py         # AES-256-GCM 封装（含 AAD）
│   │   └── keys.py           # 双层密钥：KEK 包 DEK / HKDF 扩展
│   ├── format/               # 文件格式（只认字节，不认业务语义）
│   │   ├── header.py         # 明文头结构
│   │   ├── reader.py         # 解析 + 认证校验
│   │   └── writer.py         # 序列化 + 原子写 + 备份轮转
│   ├── services/             # 业务用例（CLI 与 GUI 共用）
│   │   ├── vault_service.py  # 创建/打开/锁定/保存/改主密码
│   │   ├── entry_service.py  # 增删改查/搜索/分类/软删
│   │   └── generator.py      # 强密码生成器（secrets CSPRNG）
│   ├── io/                   # 导入导出
│   │   ├── exporter.py       # 导出 CSV/JSON（仅解锁状态）
│   │   └── importer.py       # 导入 Chrome/Edge 导出的 CSV
│   └── ui/                   # GUI 层（PySide6，只调 services，不碰 crypto/format/io）
│       ├── __init__.py
│       ├── theme.py          # citrus 设计 token → QSS + Win32 亚克力毛玻璃
│       ├── session.py        # 会话：主密码 bytearray 缓存 + 锁定清零
│       ├── dialogs.py        # 建库/解锁/改主密码/生成密码
│       ├── entry_dialog.py   # 条目新增/编辑
│       ├── main_window.py    # 主窗口：列表/详情/增删改/自动锁定
│       └── app.py            # 流程编排（建库 → 解锁 → 主窗口 → 锁定循环）
├── tests/                    # pytest，全部用临时目录不落盘
│   ├── test_kdf.py
│   ├── test_crypto.py
│   ├── test_format.py
│   ├── test_vault.py
│   ├── test_entry.py
│   ├── test_generator.py
│   ├── test_recovery.py       # P5 破坏性/恢复闭环
│   ├── test_paths.py          # 固定库路径
│   └── test_gui.py            # GUI offscreen（未装 PySide6 自动跳过）
└── docs/
    └── format-spec.md        # 文件格式二进制规范
```

**分层铁律**（学 KeePassXC）：`core` 不碰加密不碰 IO；`format` 只认字节；`cli` 一行加密代码都不许有；`ui/` 只调 services，不碰 crypto/format/io；新增框架不动核心。

## 3. 文件格式设计（.pbk）

```
┌─────────────────────────────────────────────┐
│ magic "PASSBOOK" (8B)                       │ 明文头（全部被认证）
│ format_version (u16)                        │
│ kdf_alg (u8) | memory_MiB (u32) |           │  Argon2id 参数明文，
│   iterations (u32) | parallelism (u8)       │  换机器/升级可迁移
│ salt (16B)                                  │
│ cipher_alg (u8) | iv1 (12B, 包DEK用)         │
│ iv2 (12B, 加密payload用)                    │
│ header_tag (16B) ── GCM 认证整个明文头       │  防降级篡改
├─────────────────────────────────────────────┤
│ wrapped_dek (48B) ── KEK-GCM 加密的随机 DEK  │  32B数据密钥+16B tag
│ payload ── DEK-GCM 加密，内为 gzip(JSON)     │  AEAD 自带完整性
└─────────────────────────────────────────────┘
```

密钥链：
```
主密码 ──Argon2id(盐)──▶ KEK ──GCM──▶ 包 DEK
DEK ──GCM──▶ 加密条目 JSON（gzip 压缩）
改主密码 = 只重包 DEK，库内容不动
```

## 4. 数据模型

Vault 元数据：`format_version, created_at, updated_at`

Entry 明文字段（仅索引用，尽量少）：
```
id(uuid) | type(login/note/card/identity) | folder_id | favorite
created_at | updated_at | deleted_at(软删，NULL=未删)
```

Entry 加密 JSON（`data` 字段）：`title, username, password, url, notes, tags[], 自定义字段{}`
> title 也加密（学 Proton Pass），避免"只加密了密码、URL 却明文泄露"。

## 5. CLI 命令一览

```
passbook init                       # 创建新库（设主密码）
passbook open                       # 打开库（解锁会话）
passbook lock                       # 锁定（清空内存中的 DEK/明文）
passbook add [--type login]         # 新增条目
passbook list [--folder X]          # 列表
passbook get <id|title>             # 查看（password 复制到剪贴板，45s 自动清空）
passbook search <关键词>             # 搜索（标题/用户名/URL）
passbook edit <id> / rm <id>        # 编辑 / 删除（进回收站）
passbook gen [--len 20] [--no-symbols]  # 生成强密码
passbook export json|csv            # 导出（仅解锁状态）
passbook import <file.csv>          # 导入
passbook passwd                     # 改主密码
passbook recover [--from 1|2]       # 从备份恢复（主库损坏时用）
```

> `restore` 是"从回收站恢复条目"，`recover` 是"从备份恢复整个库"，两者不同。

## 6. 开发阶段（TDD 推进）

| 阶段 | 内容 | 验收 |
|---|---|---|
| P1 加密层 ✅ 完成 | crypto + format：Argon2id/AES-GCM/文件读写/原子写/备份轮转 | 27 个单测全过（2026-09-02），含篡改/错密码/损坏文件用例 |
| P2 领域层 ✅ 完成 | core 模型（Vault/Entry/Folder）+ vault_service（创建/打开/保存/锁定/改主密码） | 52 个单测全过（2026-09-02）；改主密码仅重包 DEK，数据不重输 |
| P3 业务层 ✅ 完成 | entry_service + generator：CRUD/搜索/分类/软删/剪贴板自动清空 | 82 个单测全过（2026-09-02）；含剪贴板 45s 自动清空、标题必填、弱密码拒绝用例 |
| P4 界面层 ✅ 完成 | cli + io：全部命令 + 导入导出 + `-f` 便携路径 | 106 个单测全过（2026-09-02）；CLI 全流程走查覆盖 |
| P5 打磨 ✅ 完成 | 恢复通道（`recover` 命令 + 备份探测）+ 破坏性测试 + 打包交付 | 126 个单测全过（2026-09-04）；覆盖 payload 篡改/截断/备份同坏/密码错不动库四条事故路径 |
| P6 GUI ✅ 完成 | PySide6 界面（citrus 风格）+ 库路径固定 + 会话安全（清零/自动锁定） | 155 个单测全过（2026-09-04）；GUI offscreen 测试覆盖会话/对话框校验/主窗口流程 |
| v1.0.0 ✅ | 正式版：版本号 + CHANGELOG + 安全审计修复（KDF 参数上限 / 改密码清备份 / CSV 注入） | 155 个单测全过；审计含密码学实现正向核查 |

P5 补的两件事：

1. **恢复通道**：原先 `PayloadChecksumError` 只提示"请从备份恢复"，但没有恢复手段，
   用户得手动改 `.bak.1` 文件名。现补 `VaultService.restore_backup()`（自动挑第一个
   **真能解密**的备份，坏备份跳过；坏库另存 `.broken` 保留现场）与 `passbook recover`。
2. **破坏性测试**：`tests/test_recovery.py`，把库写坏再走完恢复闭环。

> 遗留：敏感数据清零未做。`Entry.data` 仍是 `str`（不可变），做不到覆写清零；
> 需要全链路改成 `bytearray`，涉及序列化/搜索/导出，风险与收益不匹配，暂缓。

## 7. 安全要点

- 密码生成用 `secrets`/`os.urandom`，**绝不用 `random`**
- 敏感数据用 `bytearray` 保存，锁定/删除时覆写清零（`str` 不可变做不到）
- 剪贴板复制后定时自动清空，且只在内容未被改写时才清
- 主密码比对、MAC 校验用常数时间比较
- 异常分类：`CredentialsError`(密码错) / `HeaderChecksumError`(文件篡改/非本程序文件) / `PayloadChecksumError`(上次写坏了，提示恢复备份)
- 文件权限：**不收紧 ACL**（2026-09-04 修正早期设计稿承诺）。
  库文件本身已加密，同机其他账户读到也无密可解；而便携定位下文件要跨机器
  （NTFS ACL 按 SID 记录，换台机器当前用户就打不开；FAT32/exFAT 无 ACL），
  收紧 ACL 反而破坏便携。业界主流（KeePassXC）同样不收紧库文件 ACL。

## 8. 界面风格规范（参考本机另一项目 citrus-letter-8bit，8-bit 酸橙信笺风格）

> 用户指定：界面风格参考"酸橙色信笺"项目（8-bit DAW 播放器）。

| 项 | 取值 |
|---|---|
| 纸底 | `#f2ede6`（米白信笺纸，主背景） |
| 墨色文字 | `#3a3a3a` 正文 / `#8a8a8a` 弱化 |
| 酸橙主色 | `#ed685f`（珊瑚橘红），hover/主按钮填充 |
| 深色 | `#d94f46`（hover 加深、品牌字） |
| 弱化主色 | `rgba(237,104,95,.14)` 选中底 / `.18` 描边 / `.35` 滚动条 |
| 质感 | 毛玻璃 `backdrop-filter: blur(14px) saturate(1.3)`、1px 细线分隔、9px 圆角小控件 |
| 字体 | `"Segoe UI","Microsoft YaHei",system-ui`，数字 `tabular-nums` |
| 滚动条 | 9px 细、主色半透明 thumb、圆角 |
| 交互 | 低饱和底 + 高饱和点缀；hover 填充主色反白；禁用态降透明度 |

应用范围：GUI（PySide6，QSS 实现）与 CLI 输出点缀色。token 原样定义在
`passbook/ui/theme.py`，QSS 里无自创配色。

**毛玻璃取舍（2026-09-04 返工）**：先尝试了 Win32 DWM 亚克力
（`SetWindowCompositionAttribute` + `WA_TranslucentBackground`），发现它在
远程桌面 / 虚拟机 / 系统关闭透明效果时会"调用成功但实际不渲染"，窗口整片透明
露黑底，是不可靠的视觉来源。**放弃系统级毛玻璃**：窗口铺不透明纸底 `#f2ede6`，
用"纸底 + 半透明白玻璃层控件"（`rgba(255,255,255,.6)` 卡片、`.36` 面板）近似
citrus 的玻璃质感，任何环境都不破。UI 动画（菜单/下拉弹出）同步关闭，见 `app.py`。

## 9. 参考项目（GitHub 调研）

| 项目 | 借鉴点 |
|---|---|
| KeePassXC | 目录分层（core/crypto/format/keys 分离）、KDBX4 加密组合、原子写 |
| Bitwarden | Cipher 表：type + 不透明加密 JSON、软删时间戳、双层密钥链 |
| Proton Pass | 元数据全加密、每条目独立 key 思路 |
| pass / gopass | Storage/Crypto 接口化、环境变量重定向（测试不污染生产） |
| pykeepass | 先写 .tmp 再 rename、异常体系分类、find 接口设计 |

## 10. 交付形态（单文件便携）

| 项 | 决策 |
|---|---|
| 产物 | 两个单文件 exe：`passbook.exe`（GUI，--windowed，约 49MB，PySide6 大头）+ `passbook-cli.exe`（CLI，--console，约 11MB） |
| 打包命令 | `py build.py [--gui\|--cli] [--clean]`，参数固化在 `build.py` |
| 运行依赖 | 无——目标机器不需要装 Python / 任何依赖 |
| 打包入口 | GUI 用 `run_gui.py`、CLI 用 `run.py`。都不能直接用 `passbook/__main__.py`（相对导入，打包当顶层脚本跑会 ImportError） |
| 数据文件 | `.pbk` **固定放 exe 同目录**，名字固定 `passbook.pbk`，程序内不提供选路径（见 §12） |
| 便携场景 | `passbook.exe` 拷进 U 盘任意目录双击即用；库文件自动落在 exe 旁，同进同退 |
| GUI 会话 | 解锁后主密码缓存为 bytearray（可清零），5 分钟无操作自动锁定，锁定即清零 |
| 限制 | PyInstaller 不能交叉编译：Windows exe 只能在 Windows 上打 |
| 已知坑 | Defender 对 PyInstaller 单文件偶发误报——`--noupx` 缓解；CLI 版必须显式排除 PySide6，否则 11MB 变 49MB |

**GUI 与 CLI 的分工**：GUI 是主界面（双击即用）；CLI 服务脚本、批量导入导出、
库损坏应急（`recover`）。两者共用 core/crypto/format/services，只有 `ui/` 是 GUI 独有。

**CLI 版双击（无参数）进 REPL**（早期为防"窗口一闪而过"做的）：`sys.frozen` 为真
且 argv 为空时进入交互式命令行，复用同一套 argparse，不维护第二套实现；
输入行 `lstrip("\ufeff")` 防粘贴 BOM。GUI 版不存在此问题（双击就是窗口程序）。

打包验证记录（2026-09-04）：GUI 49.0MB / CLI 10.8MB；CLI `--help` / `gen` / 退出码正常；
GUI 最小探针程序（PySide6+PyInstaller）实测启动成功、Qt platform plugin 齐全。

## 11. 明确不做（一期砍掉）

- 云同步 / 多端 / 自托管 —— 定位纯本地
- 浏览器自动填充、TOTP 动态码 —— 二期再议
- 换语言重写（C++/Rust）—— 调研过：收益（体积/启动/内存清零）换不来重写风险；
  密码学代码重写是高危操作，126+ 测试是最大的安全资产。内存清零取舍见 §12

## 12. 库路径固定与安全取舍（2026-09-04 用户决策）

**库文件固定放程序旁**（`passbook/paths.py`）：打包后 exe 同目录，源码运行当前目录。
程序不提供选择保存位置——可选路径意味着可能把库放进网盘同步目录、共享文件夹等泄露面。
CLI `-f` 保留但 `help=SUPPRESS`（自动化测试与应急恢复用），界面/帮助里不出现。

**GUI 会话内存策略**：主密码缓存为 `bytearray`，锁定时逐字节清零后丢弃引用；
5 分钟无操作自动锁定（键鼠事件重置计时器）；复制密码 45s 后仅当剪贴板未被改写才清空。

**已知取舍（不重写语言的前提下承认并记录）**：
- `Entry.data` 仍是不可变 `str`，条目敏感字段做不到覆写清零
- 真正要用主密码时需转 `str` 交给服务层，那份临时 str 生命周期短但存在
- 彻底解决需全链路 bytearray（序列化/搜索/导出），改动面与收益不匹配，不做

## 13. 目录与测试现状

```
passbook/ui/          GUI 层（theme / session / dialogs / entry_dialog / main_window / app）
run.py / run_gui.py   打包入口（CLI / GUI）
tests/test_gui.py     GUI offscreen 测试（未装 PySide6 自动跳过）
tests/test_paths.py   固定库路径测试
```

测试：155 个全过（2026-09-04，v1.0.0 正式版）。分层铁律不变：`ui/` 只调 `services/`，
不碰 crypto / format / io。
