"""命令行界面：argparse 子命令，一层加密逻辑都没有。

安全约定：
- 主密码用 getpass 不回显；init / passwd 输两次确认。
- get 默认不显示密码明文（--show 才显示明文）。
- 复制密码走 45s 自动清空。
- 弱主密码警告确认后才允许建库。
- -f 指定库文件路径 —— 便携场景：exe + .pbk 放任意目录，-f 指过去即用。
"""

import argparse
import json
import os
import shlex
import sys
from collections import Counter

from . import __version__

from .core.entry import Entry
from .core.exceptions import PassbookError, PayloadChecksumError
from .core.vault import Vault
from .io.exporter import export_csv, export_json
from .io.importer import parse_chrome_csv, parse_passbook_json
from .paths import vault_path
from .services.entry_service import EntryService, schedule_clipboard_clear
from .services.generator import generate, password_strength
from .services.vault_service import VaultService

# citrus-letter 酸橙点缀色（仅 tty 输出；NO_COLOR 或管道重定向时禁用）
_C = {
    "accent": "\x1b[38;2;237;104;95m",
    "dim": "\x1b[2m",
    "red": "\x1b[31m",
    "bold": "\x1b[1m",
    "reset": "\x1b[0m",
}
if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
    _C = {k: "" for k in _C}


# ---------- 交互原语（模块级，测试可替换） ----------
def _ask_password(prompt: str, confirm: bool = False) -> str:
    import getpass

    pw = getpass.getpass(prompt)
    if confirm:
        pw2 = getpass.getpass("再次输入（确认）：")
        if pw != pw2:
            raise PassbookError("两次输入不一致")
    return pw


def _prompt(label: str, default: str = "") -> str:
    if default:
        val = input(f"{label} [{default}]: ")
    else:
        val = input(f"{label}: ")
    return val.strip() or default


# ---------- 通用辅助 ----------
def _unlock(args) -> tuple[VaultService, EntryService, str]:
    svc = VaultService(args.file)
    pw = _ask_password("主密码：")
    vault = svc.open(pw)
    return svc, EntryService(vault), pw


def _ensure_folder(vault: Vault, name: str) -> str:
    for f in vault.folders:
        if f.name == name:
            return f.id
    return vault.add_folder(name).id


def _find_folder(vault: Vault, name: str):
    for f in vault.folders:
        if f.name == name:
            return f
    raise PassbookError(f"文件夹不存在：{name}")


def _resolve(es: EntryService, query: str, include_trash: bool = False):
    query = query.strip()
    if not query:
        raise PassbookError("需要条目的 id 或标题")
    e = es.vault.get_entry(query)
    if e is not None:
        return e
    pool = es.vault.entries if include_trash else es.vault.list_active()
    matches = [
        x for x in pool if x.id.startswith(query) or query.lower() in x.title.lower()
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(f"{m.id[:8]}({m.title})" for m in matches[:5])
        raise PassbookError(f"匹配到多个条目：{names}，请用更长前缀或完整 id")
    raise PassbookError(f"未找到条目：{query}")


def _warn_weak_password(pw: str) -> None:
    if password_strength(pw) == "weak":
        print(
            f"{_C['red']}警告：主密码偏弱{_C['reset']}"
            "（建议 >= 10 位且含大小写与数字）"
        )
        if not _prompt("仍要使用？[y/N]", "N").strip().lower() in ("y", "yes"):
            raise PassbookError("已取消")


def _print_entry(e, show_password: bool = False) -> None:
    print(f"{_C['bold']}{e.title}{_C['reset']}"
          f"{_C['dim']}  [{e.id[:8]}] [{e.type}]{_C['reset']}"
          f"{' ★' if e.favorite else ''}")
    for k, v in e.data.items():
        if k == "title":
            continue
        if k == "password":
            if not v:
                v = "（空）"
            elif not show_password:
                v = "●" * min(len(v), 12)
        print(f"  {_C['dim']}{k}{_C['reset']}: {v}")


# ---------- 子命令 ----------
def _cmd_init(args) -> int:
    if os.path.exists(args.file):
        raise PassbookError(f"文件已存在：{args.file}")
    pw = _ask_password("设置主密码：", confirm=True)
    _warn_weak_password(pw)
    VaultService(args.file).create(pw)
    print(f"{_C['accent']}已创建保险库{_C['reset']}：{args.file}")
    return 0


def _cmd_add(args) -> int:
    svc, es, pw = _unlock(args)
    data: dict = {}
    if args.title is not None:
        data["title"] = args.title.strip()
    if not data.get("title"):
        data["title"] = _prompt("标题").strip()
    if not data["title"]:
        raise PassbookError("必须填写标题")

    if args.type == "login":
        if args.username is not None:
            data["username"] = args.username
        else:
            u = _prompt("用户名", "")
            if u:
                data["username"] = u
        if args.url is not None:
            data["url"] = args.url
        else:
            url = _prompt("链接", "")
            if url:
                data["url"] = url
        if args.gen:
            if not args.password:
                args.password = generate(length=args.len)
                print(f"已生成密码：{_C['accent']}{args.password}{_C['reset']}")
        if args.password is not None:
            data["password"] = args.password
        else:
            p = _ask_password("密码（留空跳过）：")
            if p:
                data["password"] = p
        if args.notes is not None:
            data["notes"] = args.notes
    elif args.type == "note":
        if args.notes is not None:
            data["notes"] = args.notes
        else:
            n = _prompt("内容", "")
            if n:
                data["notes"] = n
    else:  # card / identity：标题 + 备注
        if args.notes is not None:
            data["notes"] = args.notes
        else:
            n = _prompt("备注", "")
            if n:
                data["notes"] = n

    folder_id = None
    if args.folder:
        folder_id = _ensure_folder(es.vault, args.folder)
    es.create(entry_type=args.type, data=data, folder_id=folder_id)
    svc.save(pw)
    print(f"已添加：{_C['bold']}{data['title']}{_C['reset']}")
    return 0


def _cmd_list(args) -> int:
    _, es, _ = _unlock(args)
    if args.trash:
        entries = es.list_trash()
    else:
        folder_id = None
        if args.folder:
            folder_id = _find_folder(es.vault, args.folder).id
        entries = es.list_entries(folder_id)
    for e in entries:
        print(f"{'★' if e.favorite else ' '} {_C['accent']}{e.id[:8]}{_C['reset']}  {e.title}")
    print(f"{_C['dim']}共 {len(entries)} 条{_C['reset']}")
    return 0


def _cmd_get(args) -> int:
    _, es, _ = _unlock(args)
    e = _resolve(es, args.query)
    _print_entry(e, show_password=args.show)
    if args.copy:
        es.copy_password(e.id)
        print(f"{_C['dim']}已复制密码，45 秒后自动清空（期间你复制了别的则不误清）{_C['reset']}")
    return 0


def _cmd_search(args) -> int:
    _, es, _ = _unlock(args)
    entries = es.search(args.query, include_trash=args.trash)
    for e in entries:
        print(f"{'★' if e.favorite else ' '} {_C['accent']}{e.id[:8]}{_C['reset']}  {e.title}")
    print(f"{_C['dim']}匹配 {len(entries)} 条{_C['reset']}")
    return 0


def _cmd_edit(args) -> int:
    svc, es, pw = _unlock(args)
    e = _resolve(es, args.query)
    print(f"编辑：{e.title}")
    data = dict(e.data)
    text_fields = ["title", "username", "url", "notes"]
    for f in text_fields:
        cur = str(data.get(f, ""))
        new = _prompt(f"{f}（回车保留）", cur)
        if new != cur:
            data[f] = new
    if data.get("password"):
        new = _ask_password("新密码（回车不变）：")
    else:
        new = _ask_password("新密码（回车跳过）：")
    if new:
        data["password"] = new
    es.update(e.id, data)
    svc.save(pw)
    print("已保存")
    return 0


def _cmd_rm(args) -> int:
    svc, es, pw = _unlock(args)
    e = _resolve(es, args.query)
    es.delete(e.id)
    svc.save(pw)
    print(f"已删除（可 restore 恢复）：{e.title}")
    return 0


def _cmd_restore(args) -> int:
    svc, es, pw = _unlock(args)
    e = _resolve(es, args.query, include_trash=True)
    es.restore(e.id)
    svc.save(pw)
    print(f"已恢复：{e.title}")
    return 0


def _cmd_purge(args) -> int:
    svc, es, pw = _unlock(args)
    e = _resolve(es, args.query, include_trash=True)
    es.purge(e.id)
    svc.save(pw)
    print(f"已彻底删除：{e.title}")
    return 0


def _cmd_purge_trash(args) -> int:
    svc, es, pw = _unlock(args)
    n = es.purge_trash()
    svc.save(pw)
    print(f"已清空回收站（{n} 条）")
    return 0


def _cmd_gen(args) -> int:
    pw = generate(
        length=args.len,
        lower=not args.no_lower,
        upper=not args.no_upper,
        digits=not args.no_digits,
        symbols=not args.no_symbols,
        exclude_ambiguous=not args.ambiguous,
    )
    print(pw)
    if args.copy:
        import pyperclip

        pyperclip.copy(pw)
        schedule_clipboard_clear(45.0, pw)
        print("已复制，45 秒后自动清空")
    return 0


def _cmd_folders(args) -> int:
    _, es, _ = _unlock(args)
    vault = es.vault
    counts = Counter(e.folder_id for e in vault.list_active())
    print(f"未分类：{counts.get(None, 0)} 条")
    for f in vault.folders:
        print(f"{f.name}：{counts.get(f.id, 0)} 条")
    return 0


def _cmd_export(args) -> int:
    _, es, _ = _unlock(args)
    if args.format == "json":
        text = export_json(es.vault, include_trash=args.trash)
    else:
        text = export_csv(es.vault)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        print(f"已导出 {len(text)} 字符 → {args.output}")
    else:
        sys.stdout.write(text)
    return 0


def _cmd_import(args) -> int:
    svc, es, pw = _unlock(args)
    with open(args.source, "r", encoding="utf-8-sig") as fh:  # 容错 BOM（浏览器导出常见）
        text = fh.read()
    vault = es.vault
    merged = 0
    if args.source.lower().endswith(".json") or text.lstrip().startswith("{"):
        data = parse_passbook_json(text)
        folder_map: dict[str, str] = {}
        for fd in data.get("folders", []):
            existing = next((f for f in vault.folders if f.name == fd["name"]), None)
            folder_map[fd["id"]] = existing.id if existing else vault.add_folder(fd["name"]).id
        for ed in data.get("entries", []):
            if vault.get_entry(ed["id"]) is not None:
                continue  # 已存在则跳过，幂等
            e = Entry.from_dict(ed)
            e.folder_id = folder_map.get(e.folder_id)
            vault.add_entry(e)
            merged += 1
    else:
        entries = parse_chrome_csv(text)
        folder_id = _ensure_folder(vault, args.folder) if args.folder else None
        for e in entries:
            e.folder_id = folder_id
            vault.add_entry(e)
            merged += 1
    svc.save(pw)
    print(f"已导入 {merged} 条（重复条目自动跳过）")
    return 0


def _cmd_recover(args) -> int:
    """从轮转备份恢复主库（与 restore 区分：restore 是回收站恢复条目）。"""
    svc = VaultService(args.file)
    pw = _ask_password("主密码（用于校验备份是否完好）：")
    used = svc.restore_backup(pw, index=args.backup_index)
    # 恢复后立刻重开一次：既是验证，也让用户看到拿到了多少条
    vault = VaultService(args.file).open(pw)
    print(f"已从 {_C['accent']}{used}{_C['reset']} 恢复，"
          f"当前库 {len(vault.list_active())} 条")
    print(f"{_C['dim']}坏库现场保留在 {args.file}.broken（确认无误后可自行删除）{_C['reset']}")
    return 0


def _cmd_passwd(args) -> int:
    old = _ask_password("当前主密码：")
    new = _ask_password("新主密码：", confirm=True)
    _warn_weak_password(new)
    VaultService(args.file).change_password(old, new)
    print("主密码已更改（库内容未动，仅重包密钥）")
    return 0


def _cmd_lock(args) -> int:
    print("CLI 是一次性命令，进程退出即释放内存，无需手动锁定")
    return 0


def _cmd_gui(args) -> int:
    """启动图形界面（主要给源码开发调试；打包版双击 exe 即是 GUI）。"""
    # importlib + 字符串模块名：刻意不让 PyInstaller 静态分析跟踪到 .ui.app，
    # 否则打 CLI 版时会把整个 PySide6 塞进去（体积 11MB → 49MB）
    import importlib

    try:
        app = importlib.import_module("passbook.ui.app")
    except ImportError:
        print("GUI 需要 PySide6：pip install PySide6-Essentials", file=sys.stderr)
        return 1
    return app.run_gui()


# ---------- 解析器 ----------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="passbook",
        description="密码本：纯本地离线密码管理器",
    )
    parser.add_argument("--version", action="version",
                        version=f"passbook {__version__}")
    # -f 刻意 help=SUPPRESS：库文件位置固定为程序旁，不向用户提供选择。
    # 保留它只为两件事——自动化测试用 tmp_path，以及库损坏时应急指定备份/库路径。
    parser.add_argument("-f", "--file", default=None, help=argparse.SUPPRESS)
    # 子命令也接受 -f（不设默认，避免覆盖主解析器的值）：
    # 这样 `passbook -f x.pbk list` 与 `passbook list -f x.pbk` 都合法
    _parent = argparse.ArgumentParser(add_help=False)
    _parent.add_argument("-f", "--file", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    def _sub(name, help):
        return sub.add_parser(name, help=help, parents=[_parent])

    sub = parser.add_subparsers(dest="command", metavar="命令")

    p = _sub("init", "创建新保险库（设主密码）")
    p.set_defaults(handler=_cmd_init)

    p = _sub("add", "新增条目")
    p.add_argument("--type", choices=("login", "note", "card", "identity"), default="login")
    p.add_argument("--folder", help="文件夹名（不存在则自动创建）")
    p.add_argument("--title")
    p.add_argument("--username")
    p.add_argument("--password")
    p.add_argument("--url")
    p.add_argument("--notes")
    p.add_argument("--gen", action="store_true", help="自动生成强密码")
    p.add_argument("--len", type=int, default=20, help="生成密码长度（配合 --gen）")
    p.set_defaults(handler=_cmd_add)

    p = _sub("list", "列出条目")
    p.add_argument("--folder", help="只列某文件夹")
    p.add_argument("--trash", action="store_true", help="列出回收站")
    p.set_defaults(handler=_cmd_list)

    p = _sub("get", "查看条目（id 或标题）")
    p.add_argument("query")
    p.add_argument("--show", action="store_true", help="显示密码明文")
    p.add_argument("--copy", action="store_true", help="复制密码到剪贴板（45s 自动清空）")
    p.set_defaults(handler=_cmd_get)

    p = _sub("search", "搜索（标题/用户名/URL）")
    p.add_argument("query")
    p.add_argument("--trash", action="store_true", help="包含回收站")
    p.set_defaults(handler=_cmd_search)

    p = _sub("edit", "编辑条目（回车保留原值）")
    p.add_argument("query")
    p.set_defaults(handler=_cmd_edit)

    p = _sub("rm", "删除条目（进回收站）")
    p.add_argument("query")
    p.set_defaults(handler=_cmd_rm)

    p = _sub("restore", "从回收站恢复")
    p.add_argument("query")
    p.set_defaults(handler=_cmd_restore)

    p = _sub("purge", "从回收站彻底删除")
    p.add_argument("query")
    p.set_defaults(handler=_cmd_purge)

    p = _sub("purge-trash", "清空回收站")
    p.set_defaults(handler=_cmd_purge_trash)

    p = _sub("gen", "生成强密码")
    p.add_argument("--len", type=int, default=20)
    p.add_argument("--no-lower", action="store_true")
    p.add_argument("--no-upper", action="store_true")
    p.add_argument("--no-digits", action="store_true")
    p.add_argument("--no-symbols", action="store_true")
    p.add_argument("--ambiguous", action="store_true", help="允许易混淆字符 0O1lI|")
    p.add_argument("--copy", action="store_true", help="复制到剪贴板")
    p.set_defaults(handler=_cmd_gen)

    p = _sub("folders", "列出文件夹")
    p.set_defaults(handler=_cmd_folders)

    p = _sub("export", "导出 json|csv")
    p.add_argument("format", choices=("json", "csv"))
    p.add_argument("-o", "--output", help="输出文件（缺省打印到 stdout）")
    p.add_argument("--trash", action="store_true", help="json 导出包含回收站")
    p.set_defaults(handler=_cmd_export)

    p = _sub("import", "导入 Chrome/Edge CSV 或 passbook JSON")
    p.add_argument("source", help="要导入的 CSV/JSON 文件")
    p.add_argument("--folder", help="CSV 导入进指定文件夹（自动创建）")
    p.set_defaults(handler=_cmd_import)

    p = _sub("recover", "从备份恢复（主库损坏时用）")
    p.add_argument("--from", dest="backup_index", type=int, choices=(1, 2),
                   help="指定备份序号（默认自动挑第一个能打开的）")
    p.set_defaults(handler=_cmd_recover)

    p = _sub("passwd", "修改主密码")
    p.set_defaults(handler=_cmd_passwd)

    p = _sub("lock", "锁定（CLI 下为提示性命令）")
    p.set_defaults(handler=_cmd_lock)

    p = _sub("gui", "启动图形界面（打包版双击 exe 即是 GUI）")
    p.set_defaults(handler=_cmd_gui)

    return parser


def _run(argv: list[str]) -> int:
    """解析并执行一条命令，含统一的错误翻译。main 与 _repl 共用同一条路径。"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "file", None) is None:
        args.file = vault_path()  # 未显式给出时才落到固定位置
    if not hasattr(args, "handler"):
        parser.print_help()
        return 1
    try:
        return args.handler(args)
    except PayloadChecksumError as e:
        print(f"{_C['red']}错误{_C['reset']}：{e}", file=sys.stderr)
        print(f"{_C['dim']}提示：运行 `passbook recover -f {args.file}` 可从备份恢复{_C['reset']}",
              file=sys.stderr)
        return 1
    except PassbookError as e:
        print(f"{_C['red']}错误{_C['reset']}：{e}", file=sys.stderr)
        return 1
    except (FileNotFoundError, IsADirectoryError) as e:
        print(f"{_C['red']}错误{_C['reset']}：{e}", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as e:
        print(f"{_C['red']}错误{_C['reset']}：{e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130


def _repl() -> int:
    """打包成 exe 后双击启动时的交互式模式。

    为什么要这个：双击 exe 等于无参数运行，print_help 完进程就退出，
    控制台窗口"闪一下就没了"。交互模式让窗口一直等着用户操作。

    输入的每一行就是一个完整的命令行（去掉 exe 名），走的还是同一套 argparse
    —— 交互模式与命令行模式行为完全一致，不维护第二套实现。

    交互模式专有（不在 argparse 里）：help 查看命令 / exit 退出。
    库文件位置固定为程序旁，这里不提供切换入口。
    """
    print(f"{_C['bold']}密码本{_C['reset']} —— 纯本地离线密码管理器")
    print(f"{_C['dim']}输入 help 查看命令，exit 退出{_C['reset']}")
    print(f"库文件：{_C['accent']}{os.path.abspath(vault_path())}{_C['reset']}")

    while True:
        try:
            # lstrip BOM：从网页/文档粘贴命令时可能带 \ufeff，不清掉会被当成子命令名
            line = input("passbook> ").strip().lstrip("\ufeff")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        head = line.lower()
        if head in ("exit", "quit", "q", "退出"):
            return 0
        if head in ("help", "?", "帮助"):
            _build_parser().print_help()
            continue

        try:
            _run(shlex.split(line))
        except SystemExit:
            pass  # argparse 已自行打印用法或错误信息，交互模式继续


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    # 只有"打包后 + 双击启动（没给任何参数）"才进交互模式：
    # 命令行下无参数仍打印 help 并返回 1，脚本可据此判断用法错误。
    if not args_list and getattr(sys, "frozen", False):
        return _repl()
    return _run(args_list)
