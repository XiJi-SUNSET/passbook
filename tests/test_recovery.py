"""P5 破坏性测试：把库写坏，然后走完整恢复闭环。

覆盖的不是"备份文件恰好能打开"，而是真实事故路径：
主库坏了 → 报错 → restore → 数据回来 → 坏库现场还在。

关键前提：备份轮转只保留 2 份，恢复**可能**丢最后一次保存的内容
（这是轮转的固有代价，不是 bug），测试如实固化这一语义。
"""

import os

import pytest

from passbook.core.entry import Entry
from passbook.core.exceptions import (
    CredentialsError,
    FormatError,
    PassbookError,
    PayloadChecksumError,
)
from passbook.services.vault_service import VaultService
from tests.conftest import PASSWORD


def _build(path, fast_params, *titles) -> VaultService:
    """建库后逐个加条目并保存，每次 save 都触发一次备份轮转。"""
    svc = VaultService(path)
    svc.create(PASSWORD, params=fast_params)
    for t in titles:
        svc.vault.add_entry(Entry(data={"title": t, "password": f"pw-{t}"}))
        svc.save(PASSWORD)
    return svc


def _titles(vault) -> set[str]:
    return {e.title for e in vault.list_active()}


def _corrupt_payload(path: str) -> bytes:
    """翻转 payload 最后一个字节（GCM tag 内）→ PayloadChecksumError。"""
    blob = bytearray(open(path, "rb").read())
    blob[-1] ^= 0x01
    open(path, "wb").write(bytes(blob))
    return bytes(blob)


# ---------- 破坏 → 报错 ----------
def test_corrupted_payload_raises_checksum(vault_path, fast_params):
    _build(vault_path, fast_params, "A", "B")
    _corrupt_payload(vault_path)
    with pytest.raises(PayloadChecksumError):
        VaultService(vault_path).open(PASSWORD)


def test_truncated_file_raises_format(vault_path, fast_params):
    """写入被中断（如断电）导致文件被截断到头都不完整。"""
    _build(vault_path, fast_params, "A", "B")
    with open(vault_path, "r+b") as f:
        f.truncate(30)
    with pytest.raises(FormatError):
        VaultService(vault_path).open(PASSWORD)


def test_header_tag_truncated_raises_credentials(vault_path, fast_params):
    """截到头之后、tag 之前：tag 长度不足，按"密码错/被篡改"处理。"""
    _build(vault_path, fast_params, "A", "B")
    with open(vault_path, "r+b") as f:
        f.truncate(70)
    with pytest.raises(CredentialsError):
        VaultService(vault_path).open(PASSWORD)


# ---------- 破坏 → 恢复 ----------
def test_restore_recovers_data_after_payload_corruption(vault_path, fast_params):
    _build(vault_path, fast_params, "A", "B")
    _corrupt_payload(vault_path)

    used = VaultService(vault_path).restore_backup(PASSWORD)
    assert used == f"{vault_path}.bak.1"

    vault = VaultService(vault_path).open(PASSWORD)
    # bak.1 是"加 B 之前"的快照：A 回来了，B 不在——轮转备份的固有语义
    assert _titles(vault) == {"A"}


def test_restore_keeps_broken_file_as_evidence(vault_path, fast_params):
    _build(vault_path, fast_params, "A", "B")
    broken_bytes = _corrupt_payload(vault_path)

    VaultService(vault_path).restore_backup(PASSWORD)
    assert open(f"{vault_path}.broken", "rb").read() == broken_bytes
    # 备份链本身没被破坏，用户仍可再选 bak.2
    assert os.path.exists(f"{vault_path}.bak.1")
    assert os.path.exists(f"{vault_path}.bak.2")


def test_restore_works_even_when_vault_cannot_open_at_all(vault_path, fast_params):
    """恢复只读备份、不读主库：主库坏成什么样都能救。"""
    _build(vault_path, fast_params, "A", "B")
    with open(vault_path, "r+b") as f:
        f.truncate(30)
    with pytest.raises(FormatError):
        VaultService(vault_path).open(PASSWORD)

    VaultService(vault_path).restore_backup(PASSWORD)
    assert _titles(VaultService(vault_path).open(PASSWORD)) == {"A"}


def test_restore_skips_corrupted_newer_backup(vault_path, fast_params):
    """bak.1 也坏了 → 自动退到 bak.2，而不是恢复出一个坏库。"""
    _build(vault_path, fast_params, "A", "B")
    _corrupt_payload(vault_path)
    _corrupt_payload(f"{vault_path}.bak.1")  # 较新的备份同坏

    used = VaultService(vault_path).restore_backup(PASSWORD)
    assert used == f"{vault_path}.bak.2"
    # bak.2 是初始空库
    assert VaultService(vault_path).open(PASSWORD).list_active() == []


def test_probe_backup_distinguishes_good_from_bad(vault_path, fast_params):
    svc = _build(vault_path, fast_params, "A", "B")
    assert svc.probe_backup(f"{vault_path}.bak.1", PASSWORD) == 1
    _corrupt_payload(f"{vault_path}.bak.1")
    assert svc.probe_backup(f"{vault_path}.bak.1", PASSWORD) is None
    assert svc.probe_backup(f"{vault_path}.bak.1", "wrong-password") is None


# ---------- 该失败的必须失败 ----------
def test_restore_without_any_backup_fails(vault_path, fast_params):
    svc = _build(vault_path, fast_params, "A")
    for b in svc.list_backups():
        os.remove(b)
    with pytest.raises(PassbookError, match="没有找到备份"):
        svc.restore_backup(PASSWORD)


def test_restore_wrong_password_does_not_touch_vault(vault_path, fast_params):
    """密码不对时绝不能覆盖主库——否则会把好库换成坏库。"""
    _build(vault_path, fast_params, "A", "B")
    broken = _corrupt_payload(vault_path)
    with pytest.raises(PassbookError, match="没有一份备份"):
        VaultService(vault_path).restore_backup("wrong-password")
    assert open(vault_path, "rb").read() == broken  # 主库原样未动


def test_restore_explicit_index_out_of_range(vault_path, fast_params):
    svc = _build(vault_path, fast_params, "A")
    with pytest.raises(PassbookError, match="备份序号"):
        svc.restore_backup(PASSWORD, index=9)


def test_restore_explicit_index_verifies_before_writing(vault_path, fast_params):
    svc = _build(vault_path, fast_params, "A", "B")
    _corrupt_payload(vault_path)
    _corrupt_payload(f"{vault_path}.bak.1")
    with pytest.raises(PassbookError, match="无法用当前主密码打开"):
        svc.restore_backup(PASSWORD, index=1)  # 明确指定就得是它，不允许悄悄换


# ---------- CLI 端到端 ----------
def test_cli_restore_end_to_end(vault_path, fast_params, monkeypatch, capsys):
    import passbook.cli as cli

    from tests.test_cli import FakeInputs

    _build(vault_path, fast_params, "A", "B")
    _corrupt_payload(vault_path)

    # 正常命令先报错，并指向 recover
    monkeypatch.setattr(cli, "_ask_password", FakeInputs(PASSWORD))
    assert cli.main(["-f", str(vault_path), "list"]) == 1
    assert "recover" in capsys.readouterr().err

    monkeypatch.setattr(cli, "_ask_password", FakeInputs(PASSWORD))
    assert cli.main(["-f", str(vault_path), "recover"]) == 0
    out = capsys.readouterr().out
    assert "bak.1" in out
    assert "1 条" in out

    monkeypatch.setattr(cli, "_ask_password", FakeInputs(PASSWORD))
    assert cli.main(["-f", str(vault_path), "list"]) == 0
    assert "A" in capsys.readouterr().out
