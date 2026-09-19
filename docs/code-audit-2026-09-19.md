# 密码本 Passbook — 代码审计报告

> 审计对象：`I:\AI Workspace\passbook`（main @ `93a2656`，v1.0.1）
> 审计日期：2026-09-19
> 审计范围：全部 35 个源文件（约 5 800 行）+ 51 个测试 + 设计文档
> 方法：逐文件通读 + 在最外层接口构造反例复现。所有结论均有可执行证据，
> 复现脚本在临时目录运行，未触碰任何真实库文件。

## 0. 结论摘要

代码整体质量偏高：分层干净、异常语义明确、加密原语选型正确、测试覆盖了真实的
事故路径（破坏→恢复闭环）。**未发现任何密码学实现层面的错误** —— Argon2id 参数
校验、GCM 的 AAD 绑定、常数时间比较、`secrets` 随机源都经得起推敲。

问题集中在**"承诺与实现不一致"**这一类：代码在若干处向用户许下了安全承诺，
但实现路径无法兑现。其中 2 处会直接损害用户利益（密码被写坏、剪贴板不清空），
3 处属于设计意图落空。基线状态：**155 个测试全过，但上述问题全部在测试盲区里**。

| 级别 | 数量 | 性质 |
|---|---|---|
| P0 | 2 | 安全承诺失效 / 用户数据被改坏 |
| P1 | 1（含 6 处文档连带） | 设计意图落空，文档与实现不符 |
| P2 | 4 | 未捕获异常，用户看到 traceback |
| P3 | 14 | 一致性、健壮性、性能、可维护性 |
| 测试盲区 | 5 | 上述问题未被任何测试覆盖的原因 |

---

## 1. P0 级问题

### 1.1 CLI 的"45 秒自动清空剪贴板"从未生效

**位置**：`passbook/services/entry_service.py:116-135`、`passbook/cli.py:217,304`

`schedule_clipboard_clear` 用 `threading.Timer` 实现延时清空，并显式设了
`daemon = True`：

```python
_clipboard_timer = threading.Timer(ttl, _do)
_clipboard_timer.daemon = True     # ← 致命
_clipboard_timer.start()
```

而 CLI 的调用路径是：`_cmd_get()` 返回 → `_run()` 返回 → `main()` 返回 → 进程退出。
Python 的 `threading._shutdown()` **只等待非 daemon 线程**，daemon 线程在解释器
退出时被直接丢弃。定时器根本来不及触发，进程就没了。

**复现证据**（子进程走真实调用路径，`pyperclip` 替换为写日志的假实现，未触碰真实剪贴板）：

```
CLI 场景：命令执行完 → 进程立刻退出（daemon Timer）
  [daemon] 子进程退出码=0  日志=['SCHEDULED']
   → 定时器回调执行了吗： False

对照组：同一份逻辑，但主线程 sleep 到定时器触发
  [waiting] 子进程退出码=0  日志=['SCHEDULED', "COPY:''"]
   → 定时器回调执行了吗： True
```

对照组证明逻辑本身没问题，纯粹是"进程不等 daemon 线程"导致回调被丢弃。

**影响**：`passbook get X --copy` 会打印
"已复制密码，45 秒后自动清空（期间你复制了别的则不误清）" —— 这句话是假的。
密码会一直留在系统剪贴板里，直到被其他内容覆盖。这正是密码管理器最典型的泄露面
（剪贴板历史、其他程序读取剪贴板）。`gen --copy` 同理。

**修复方向**（三选一，按推荐度排序）：

1. **改成非 daemon + 显式等待**。清空剪贴板是"用户已经拿到密码、可以立刻粘贴"之后
   的事，阻塞 45 秒对 CLI 不可接受，所以更好的做法是：
2. **缩短 CLI 的 TTL 并显式 join**（例如 5 秒），或让 CLI 用一句
   `input("按回车清空剪贴板…")` 把控制权交给用户。CLI 场景下"用户按回车"比"等 45 秒"
   更符合直觉。
3. **最保守：CLI 不提供 `--copy`**，只保留 `--show`，把剪贴板能力留给 GUI
   （GUI 有事件循环，`QTimer` 工作正常）。

无论选哪个，都必须同步修改那句提示语，不能让输出撒谎。

### 1.2 CSV 导出给密码加了 `'` 前缀，导出再导入密码就错了

**位置**：`passbook/io/exporter.py:26-35, 63-66`

`_csv_safe` 用来防 Excel/Sheets 的公式注入（`= + - @` 开头的单元格会被当公式执行），
这个防护本身是对的。问题是它被**无差别地应用到了所有列**：

```python
writer.writerow(
    [_csv_safe(e.data.get(k, "")) for k in
     ("title", "url", "username", "password", "notes")]   # ← password 也在里面
)
```

函数的 docstring 自己也承认代价是"极少数以 `= + - @` 开头的值（如**标题**）走浏览器
导入时会带上 `'` 前缀" —— 但它没意识到密码同样会中招，而密码一旦被改，用户是**登录不进
去的**，且很难排查。

**复现证据**：

```
导出 CSV：
  name,url,username,password,note
  U,https://x,u,'-Passw0rd!,
  V,https://y,u,'@home2026,
回读密码： ["'-Passw0rd!", "'@home2026"]
[确认为真] 密码被加 ' 前缀，往返失真
```

**修复**：公式注入的风险只在"用 Excel/Sheets **打开**这个 CSV"时存在。
`password` 列导出后是给浏览器/KeePass/Bitwarden **导入**用的，这些程序不会把该列
当公式求值。因此：

- `title` / `url` / `username` / `notes` → 保留 `_csv_safe`
- `password` → **原样输出**

如果仍不放心（比如担心用户真的用 Excel 打开），可以在导出时给一次警告，但绝不能
改密码本身的内容。另外建议给 `_csv_safe` 加一条自解释的注释，说明为什么密码列例外。

---

## 2. P1 级问题

### 2.1 "双层密钥"是空转的 —— 改主密码实际是整体重加密

**位置**：`services/vault_service.py:43-64`、`format/writer.py:34-59`

这是本次审计最值得玩味的一处：**架构搭对了，但没接上**。

设计意图（`DESIGN.md` §1、§3，`crypto/keys.py` 模块 docstring）写得非常清楚：

```
主密码 ──Argon2id(盐)──▶ KEK ──GCM──▶ 包 DEK
DEK ──GCM──▶ 加密条目 JSON
改主密码 = 只重包 DEK，库内容不动
```

DEK 间接层存在的**唯一理由**，就是让"换主密码"退化为"换一把 KEK 重新包一次 DEK"，
而不必碰体积最大的 payload。但实现里：

```python
# writer.save()
params = params or KdfParams()      # ← 没传 params 时，生成全新随机 salt
header = Header.new(params)          # ← dek_iv / payload_iv 也都是新的
...
dek = generate_dek()                 # ← 每次保存都生成新 DEK
```

而 `VaultService.save()` 调用时**从不传 `params`**：

```python
def save(self, password: str) -> None:
    payload = json.dumps(self._vault.to_dict(), ...).encode("utf-8")
    save_file(self.path, password, payload)      # ← params 缺省 = None
```

于是每次保存：salt 换新 → KEK 换新 → DEK 换新 → **整个 payload 重新加密**。
`change_password` 走的是同一条 `save_file` 路径，所以它也是整体重加密。

**复现证据**：

```
1. 每次 save 是否都重新生成 salt / DEK？
  保存前 salt      : 8e4d324d07ec3504026c0bda885cb0cc
  保存后 salt      : 183e849b5bd5baeac45e7dba8ea0d683 → 变了
  保存前 wrapped_dek: 6c946a189a57a9453aecd8f04a754d04
  保存后 wrapped_dek: 7bb5f839085ce33841a02d0d8957f504 → 变了
[确认为真]

2. change_password 是"只重包 DEK"还是"整体重加密"？
  payload_iv 变化: 5bac571b1882bd3a2b565cf9 → 9086993102ce4d8cdc97b7e5
  payload 密文相同: False  (长度 342 → 342)
[确认为真] 整块 payload 被重新加密 —— 与"库内容不重加密"的宣称矛盾
```

**连带影响：6 处面向用户的文案在撒谎**

| 位置 | 原文 |
|---|---|
| `README.md:10` | "双层密钥——改主密码毫秒级完成" |
| `README.md:73` | "`passwd` 改主密码（库内容不重加密）" |
| `crypto/keys.py:7-8` | "改主密码 = 重新派生 KEK 再重包一次 DEK，库内容完全不用重加密" |
| `services/vault_service.py:55` | "改主密码：……毫秒级（数据不重输）" |
| `ui/dialogs.py:185,196` | "库内容不重加密，只重包数据密钥" / "瞬间完成" |
| `ui/main_window.py:454` | 弹窗"主密码已更改（库内容未重新加密）" |
| `cli.py:383` | "主密码已更改（库内容未动，仅重包密钥）" |

另外 `DESIGN.md` §6 的 P2 验收标准写的是"改主密码仅重包 DEK，数据不重输"，
但这个验收条件**从未被任何测试固化**。

**修复方向**：

- **方向 A（让实现追上设计，推荐）**：把 DEK 与 salt 的生命周期从"每次保存"改为
  "每个库"。
  - `create()` 时生成 DEK 并落盘 `wrapped_dek`；会话内把 DEK 缓存在内存
    （`VaultService` 已有 `_vault`，加一个 `_dek` 不难，`lock()` 时一并清零）。
  - `save()` 复用现有 header 的 salt / dek_iv，**只换 payload_iv**，用同一个 DEK 加密。
  - `change_password()` 才换 salt，用新 KEK 重包**同一个 DEK**，payload 原样搬运。
  - 这样既兑现了"毫秒级"，也让 DEK 间接层真正物有所值。
- **方向 B（改文档）**：如果认为"每次保存换新 DEK"在密码学上更保守、不愿动实现，
  那就把这 7 处文案统一改成"改主密码会重新加密整个库"。以当前库规模（几百条、
  几百 KB）重加密本来就是毫秒级，改文案成本最低。

无论选哪个，**必须让文档、代码注释、UI 文案三者一致** —— 目前的状态比单纯的
"实现有偏差"更糟：它会让后续维护者基于错误的心智模型做决策。

---

## 3. P2 级问题：未捕获异常

`cli.py:527-545` 的 `_run` 捕获了 `PayloadChecksumError`、`PassbookError`、
`FileNotFoundError`、`IsADirectoryError`、`ValueError`、`JSONDecodeError`、
`KeyboardInterrupt` —— **唯独没捕 `KeyError`**。而 `core` 层的反序列化代码大量
使用 `d["key"]` 下标访问。

### 3.1 库文件字段缺失 → 裸 KeyError

`Entry.from_dict`（`core/entry.py:100-109`）用 `d["id"]`、`d["type"]`、
`d["created_at"]`、`d["updated_at"]`；`Folder.from_dict`（`core/vault.py:25`）同理。

**复现证据**（构造一个能正常解密、但条目缺字段的库）：

```
实际异常: KeyError → 'created_at'
[确认为真] 裸 KeyError 逃逸，未被翻译成 PassbookError，UI 会显示 traceback
```

触发条件不苛刻：库文件被外力损坏、跨版本读写、手工编辑过 JSON 再导回，
都可能撞上。用户此时需要的是"文件已损坏，请用 recover 恢复"，
而不是一个 `KeyError: 'created_at'` 堆栈。

**修复**：`from_dict` 里改用 `d.get("落")` 兜底默认值，或在 reader/service 边界把
`KeyError` 统一翻译成 `FormatError("库文件结构不完整")`。

### 3.2 导入 JSON 缺 `id` → 裸 KeyError

`cli.py:347`：

```python
if vault.get_entry(ed["id"]) is not None:      # ← ed 没有 id 就炸
```

**复现证据**：

```
抛: KeyError → 'id'
[确认为真] _cmd_import 直接用 ed['id']，缺失字段时崩在 KeyError
```

**修复**：导入前校验必填字段，缺失时给出"第 N 条缺少 id 字段"这样的可定位报错。

### 3.3 交互模式被一个引号打死

`cli.py:580-583`：

```python
try:
    _run(shlex.split(line))
except SystemExit:
    pass          # ← 只捕 SystemExit
```

`shlex.split('get "foo')` 抛 `ValueError: No closing quotation`，而 `ValueError`
不在这里的捕获范围内，于是异常冲出 `while` 循环、冲出 `_repl`、终止整个会话。

**复现证据**：

```
shlex.split 抛: ValueError → No closing quotation
[确认为真] _repl 只捕获 SystemExit，ValueError 会一路冒出去终止整个交互会话
```

后果很讽刺：`_repl` 存在的**目的**就是"防止控制台窗口一闪而过"，
结果一个手滑的引号就让窗口闪退了。

**修复**：把 `except SystemExit` 扩成 `except (SystemExit, ValueError)`，
或在 `_repl` 里包一层。

### 3.4 `change_password` 静默丢弃未保存的内存改动

`vault_service.py:60`：`vault = self.open(old_password)` —— 这会**重建整个
`self._vault`**。如果调用方在此之前改过内存但没 `save()`，那些改动会无声消失。

**复现证据**：

```
改密码后磁盘上的条目: ['已保存']
内存里的条目      : ['已保存']
[确认为真] change_password 内部 open() 重建对象，未保存的内存改动被静默丢弃
```

GUI 每条操作后都 `save()`，碰不到；但这是 service 层的隐藏副作用，
将来任何"攒一批改动再统一保存"的优化都会踩中它。

**修复**：`change_password` 内部改用不写入 `self._vault` 的校验方式
（例如直接 `load()` + `json.loads` 验密码），避免副作用。

---

## 4. P3 级问题

### 4.1 一致性

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 1 | `cli.py:360-361` | CSV 导入**没有任何去重**，但结尾固定打印"已导入 N 条（重复条目自动跳过）"；只有 JSON 路径靠 `get_entry(ed["id"])` 去重 | 按 (title, username, url) 去重，或把提示语改成按路径区分。实测同一份 CSV 连导两次得到 2 条重复 |
| 2 | `passbook/__init__.py:3` | `__version__ = "1.0.0"`，而 `pyproject.toml` 与 `CHANGELOG` 都是 `1.0.1`。`passbook --version` 会输出错误版本 | 统一到 1.0.1，并考虑从 `importlib.metadata` 单一来源取值 |
| 3 | `ui/main_window.py:440-444` | `_generate` 复制密码后提示"45 秒后自动清空"，但**从未调用 `QTimer.singleShot`**，也没设 `self._copied`。`dialogs.py:327` 的 `GeneratorDialog._copy` 同样 | 复用 `_copy_password` 的清空逻辑 |
| 4 | `ui/dialogs.py:177-181` | `UnlockDialog.get` 是**死代码**，且有求值顺序 bug：`(dlg.password, dlg.exec() == ...)` 先读空密码再 `exec()`，永远返回 `("", False)` | 删除，或按 `GeneratorDialog.get` 的写法先 `exec()` 再取属性 |
| 5 | `ui/dialogs.py:225-231`、`main_window.py:447-454` | GUI 让用户填"当前主密码"，但 `old_password` **从未被使用** —— 实际用的是会话缓存值。输入框纯摆设，打错了也能改成功 | 要么用它做校验，要么去掉这个输入框 |
| 6 | `cli.py:38` | `if os.environ.get("NO_COLOR") or ...` —— `NO_COLOR=`（空值）被当成未设置。而 [NO_COLOR 规范](https://no-color.org) 要求"变量存在即禁用，无论值为何" | 改成 `if os.environ.get("NO_COLOR") is not None or ...` |
| 7 | `core/entry.py:62`、`core/vault.py:28` | `@dataclass` 默认 `eq=True` → `Entry` **不可哈希**（`__hash__` 被置空），且 `entries.index()` / `remove()` 按**值**比较而非身份。`vault.py:53,80,87` 依赖它 | 加 `eq=False`，按身份比较更符合"实体"语义，也顺带恢复可哈希 |

`Entry` 的验证输出：

```
Entry 可哈希吗: 不可以 → unhashable type: 'Entry'
e1 == e2（id 不同）: False
用一个"值相同但不同对象"去 index: 0 （命中的是 e1 的位置，靠 id 相同侥幸）
```

目前因为 `id` 唯一所以没出错，但这是"侥幸正确"，不是"设计正确"。

### 4.2 健壮性

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 8 | `core/vault.py:163-174` | 注释说"过新版本拒绝加载，防止静默丢字段"，但**先构造完所有对象才检查版本**（实测 `cls(...)` 在检查之前）。且抛 `ValueError` 而非 `FormatError`，与异常体系不一致 | 把版本检查提到函数开头，抛 `FormatError` |
| 9 | `format/writer.py:88-95` | `atomic_write` 只 `fsync` 文件本身，**没 fsync 父目录**。POSIX 上 `rename` 的持久化需要目录 fsync，断电后可能回退到旧文件 | 非 Windows 平台补 `os.open(dir, O_DIRECTORY)` + `fsync`（Windows 影响很小，可条件跳过） |
| 10 | `format/writer.py:57-58` | `_rotate_backup` 在写新文件**之前**执行。若新文件写入失败，原文件已被挪到 `.bak.1`（仍可救回，但主路径上不再有可用库） | 可接受，但建议在 docstring 里写明这个次序及其代价 |
| 11 | `format/writer.py:90` | `.tmp` 用固定名，无并发保护 | 单用户应用可接受，加 `os.getpid()` 后缀更稳 |
| 12 | `core/vault.py:46-47, 49-56` | `get_entry` 是 O(n) 线性扫描，`update_entry` 里还要再 `index()` 一次 O(n) | 加 `_index: dict[str, int]` 或 `dict[str, Entry]`，几行代码换整层查询从 O(n)→O(1) |

性能实测（2 万条目）：

```
2 万条目下做 100 次 get_entry：17.5 ms
```

当前规模（几百条）完全无感，属于"以后想起来再说"级别。

### 4.3 可维护性

| # | 位置 | 问题 |
|---|---|---|
| 13 | `crypto/keys.py:20-21` vs `format/reader.py:27-28` | `HEADER_TAG_LEN` / `WRAPPED_DEK_LEN` 在两个模块各定义一份，值相同。应单一来源 |
| 14 | `format/reader.py:86-89` | `_const_time_eq` 在函数体内 `import hmac`，应提到模块顶部 |
| 15 | `ui/main_window.py:402` | `self._current.favorite = dlg.favorite()` 直接改对象，绕过 `vault.update_entry`，导致 `updated_at` / `vault.updated_at` 不更新（因随后整体 save 所以数据没丢） |
| 16 | `ui/main_window.py:513-519, 526-529` | `eventFilter` 装到 QApplication 后，`closeEvent` 里没有 `removeEventFilter`。窗口重建期间旧过滤器可能仍在重置计时器 |
| 17 | `services/generator.py:104-118` | 主密码强度门偏松：只数长度与字符类别，`"aaaaaaaaaa11"`（12 位、2 类）会被判为 `"ok"` 而放行；`entropy_bits` 对人工密码用实际字符集估算，明显偏乐观（docstring 已诚实标注） |
| 18 | `io/importer.py:41-52` | CSV 导入时把 5 个字段全写进 `data`，即使是空串。会让 `_print_entry` 打印一堆空字段，也略微膨胀 payload |

### 4.4 测试盲区

以下 5 个盲区正好对应上面的大部分问题 —— **测试没有失败，不代表行为正确**：

| 盲区 | 相关测试 | 为什么没抓到 |
|---|---|---|
| CLI 剪贴板清空 | 无 | 完全没有测试覆盖 CLI 的 `--copy` 路径，`test_entry_service.py` 只测了 `schedule_clipboard_clear` 函数本身 |
| GUI 生成的密码不清空 | `test_gui.py:229-232` | 测试**直接调用** `win._clear_clipboard()`，绕过了定时器注册路径，所以 `_generate` 缺 timer 完全测不出来 |
| 改主密码是否重加密 payload | `test_gui.py:78-88` | 只断言了密码缓冲区被换掉，没有断言 payload 密文保持不变 —— 而后者才是设计承诺的核心 |
| CSV 往返保真 | `test_gui.py:284-293` | 只断言了表头和几个字段"在"，没断言密码能原样回来 |
| 导入缺字段的健壮性 | 无 | 没有负面用例 |

**建议新增的回归测试**（可直接用本次审计的复现脚本改造）：

```
tests/test_clipboard_cli.py     # 子进程验证 CLI 复制后确实会被清空
tests/test_roundtrip_csv.py     # 密码含 = + - @ 前缀的往返保真
tests/test_import_malformed.py  # 缺 id / 缺 created_at 应报 PassbookError
tests/test_rekey.py             # change_password 后 payload 密文不变（方向 A）
tests/test_repl.py              # 交互模式遇畸形输入不退出
```

---

## 5. 值得肯定的地方

写报告不能只挑毛病，以下几处做得确实好，重构时**不要动**：

- **异常语义分层**（`core/exceptions.py`）：三类异常对应三种完全不同的用户行动建议，
  且 `CredentialsError` 刻意合并"密码错"与"头被篡改"以防解密预言机探测 —— 这是有
  密码学素养的设计，不是随手写的。
- **KDF 参数 DoS 防护**（`crypto/kdf.py:16-20` + `format/reader.py:42-45`）：
  意识到"文件头此刻还没通过 HMAC 认证"，因此在派生密钥前就约束
  memory/iterations 上限，把恶意文件的内存炸弹挡在门外。这个顺序很关键，做对了。
- **AAD 绑定完整**：`wrapped_dek` 用 `header_plain` 作 AAD，
  `payload` 用 `header_plain + wrapped_dek` 作 AAD。任何一处字节被改都会导致认证失败，
  不存在"改了参数还能解密"的降级缝隙。
- **原子写 + 备份轮转**（`format/writer.py`）：先写 `.tmp` → fsync → rename，
  绝不 truncate 原文件。配套的 `recover` 会**先真解密验证**备份完好再恢复，
  坏备份自动跳过，坏库另存 `.broken` 留现场 —— 这套恢复语义在业余项目里相当罕见。
- **`build.py --clean` 的血泪教训**（`build.py:77-95`）：注释记录了曾用
  `rmtree(dist)` 误删用户库文件的事故，现在的实现只删 `.exe`/`.spec` 并**列印保留的
  数据文件**。这种"把事故写进代码"的做法值得保持。
- **`userinfo` 层的诚实标注**：`session.py` 的 docstring 主动写明"bytearray 只解决了
  缓存的那一份，临时 str 逃不掉"，`DESIGN.md` §12 也记录了取舍。知道自己没做到什么，
  比假装做到了更有价值。

---

## 6. 修复优先级建议

如果只做三件事，按顺序做：

1. **修 CSV 密码列**（1.2）—— 一行改动，但直接防止用户丢密码。风险极低。
2. **修 CLI 剪贴板**（1.1）—— 让提示语不再撒谎。若暂时不想改实现，
   至少先把那句"45 秒后自动清空"去掉。
3. **对齐"改主密码"的叙事**（2.1）—— 要么按方向 A 接上 DEK 间接层，
   要么按方向 B 改掉 7 处文案。**不要放任文档与实现互相矛盾。**

剩下 P2/P3 可以打包进 v1.0.2 一起处理，都是一两个小时量级的改动。

---

## 附录：审计方法与可复现性

- 全文通读：`passbook/` 下 30 个源文件、`tests/` 15 个测试文件、4 份文档
- 动态验证：构造 9 个独立反例，全部在 `tempfile.mkdtemp()` 中进行
- 剪贴板验证采用**子进程 + 假 pyperclip**方案，未读写用户真实剪贴板
- 库文件操作只发生在临时目录，`git status` 审计前后均为干净
- 基线测试：`pytest -q` → **155 passed in 10.78s**
- 环境：Python 3.12.4 / argon2-cffi 25.1.0 / cryptography 48.0.0 / PySide6 6.11.0
