"""库文件路径：固定放程序旁，不给用户选位置。"""

import os
import sys

import pytest

from passbook.paths import VAULT_FILENAME, vault_dir, vault_path


def test_vault_dir_is_cwd_when_running_from_source(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    assert vault_dir() == str(tmp_path)
    assert vault_path() == str(tmp_path / VAULT_FILENAME)


def test_vault_dir_is_exe_dir_when_frozen(tmp_path, monkeypatch):
    """打包后库文件必须落在 exe 同目录——便携模式的全部前提。"""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "passbook.exe"))
    assert vault_dir() == str(tmp_path)
    assert vault_path() == str(tmp_path / VAULT_FILENAME)


def test_vault_path_is_absolute_and_stable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = vault_path()
    assert os.path.isabs(first)
    assert vault_path() == first  # 同一进程内不因任何状态变化而漂移
