"""VaultService 生命周期测试：创建/打开/保存/锁定/改主密码。"""

import os

import pytest

from passbook.core.entry import Entry
from passbook.core.exceptions import CredentialsError, PassbookError
from passbook.services.vault_service import VaultService
from tests.conftest import PASSWORD


def test_create_writes_file_and_opens(vault_path, fast_params):
    svc = VaultService(vault_path)
    vault = svc.create(PASSWORD, params=fast_params)
    assert svc.unlocked
    assert vault.entries == []

    svc2 = VaultService(vault_path)
    reopened = svc2.open(PASSWORD)
    assert reopened.entries == []
    assert reopened.created_at == vault.created_at


def test_create_rejects_when_already_open(vault_path, fast_params):
    svc = VaultService(vault_path)
    svc.create(PASSWORD, params=fast_params)
    with pytest.raises(PassbookError):
        svc.create(PASSWORD)


def test_open_wrong_password(vault_path, fast_params):
    svc = VaultService(vault_path)
    svc.create(PASSWORD, params=fast_params)
    with pytest.raises(CredentialsError):
        VaultService(vault_path).open("nope")


def test_save_persists_changes(vault_path, fast_params):
    svc = VaultService(vault_path)
    vault = svc.create(PASSWORD, params=fast_params)
    vault.add_entry(Entry(data={"title": "Gmail", "username": "x", "password": "y"}))
    svc.save(PASSWORD)

    reopened = VaultService(vault_path).open(PASSWORD)
    assert len(reopened.list_active()) == 1
    assert reopened.list_active()[0].data["title"] == "Gmail"


def test_lock_drops_plaintext(vault_path, fast_params):
    svc = VaultService(vault_path)
    svc.create(PASSWORD, params=fast_params)
    svc.lock()
    assert not svc.unlocked
    with pytest.raises(PassbookError):
        _ = svc.vault


def test_change_password_rekeys(vault_path, fast_params):
    svc = VaultService(vault_path)
    vault = svc.create(PASSWORD, params=fast_params)
    vault.add_entry(Entry(data={"title": "QQ", "username": "u", "password": "p"}))
    svc.save(PASSWORD)

    svc.change_password(PASSWORD, "new-master-2026")

    # 旧密码失效，新密码可开，数据完好
    with pytest.raises(CredentialsError):
        VaultService(vault_path).open(PASSWORD)
    reopened = VaultService(vault_path).open("new-master-2026")
    assert reopened.list_active()[0].data["title"] == "QQ"


def test_change_password_discards_old_backups(vault_path, fast_params):
    """改主密码后旧备份必须清除——它们仍用旧密码加密，留着等于没改。"""
    svc = VaultService(vault_path)
    vault = svc.create(PASSWORD, params=fast_params)
    vault.add_entry(Entry(data={"title": "A", "password": "x"}))
    svc.save(PASSWORD)
    assert os.path.exists(f"{vault_path}.bak.1")

    svc.change_password(PASSWORD, "new-master-2026")
    assert not os.path.exists(f"{vault_path}.bak.1")
    assert not os.path.exists(f"{vault_path}.bak.2")
    # 新密码能开、旧密码失效
    assert VaultService(vault_path).open("new-master-2026").list_active()[0].title == "A"
    with pytest.raises(CredentialsError):
        VaultService(vault_path).open(PASSWORD)


def test_change_password_wrong_old_fails(vault_path, fast_params):
    svc = VaultService(vault_path)
    svc.create(PASSWORD, params=fast_params)
    with pytest.raises(CredentialsError):
        svc.change_password("wrong-old", "whatever")


def test_save_after_lock_requires_unlock(vault_path, fast_params):
    svc = VaultService(vault_path)
    svc.create(PASSWORD, params=fast_params)
    svc.lock()
    with pytest.raises(PassbookError):
        svc.save(PASSWORD)
