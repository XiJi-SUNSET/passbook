"""条目业务编排测试：创建校验、部分更新、文件夹、收藏、软删、剪贴板。"""

import sys
import time

import pytest

from passbook.core.vault import Vault
from passbook.services.entry_service import EntryService
from passbook.services.entry_service import schedule_clipboard_clear
from passbook.core.exceptions import PassbookError


class FakeClipboard:
    """测试用剪贴板替身（pyperclip 延迟导入，monkeypatch sys.modules）。"""

    content = ""

    @classmethod
    def copy(cls, text: str) -> None:
        cls.content = text

    @classmethod
    def paste(cls) -> str:
        return cls.content


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyperclip", FakeClipboard)
    return EntryService(Vault())


def test_create_requires_title(service):
    with pytest.raises(PassbookError):
        service.create(data={"username": "u"})


def test_create_login(service):
    e = service.create(data={"title": "GitHub", "username": "xi", "password": "p@ss"})
    assert e.type == "login"
    assert service.get(e.id).title == "GitHub"


def test_create_with_folder(service):
    f = service.vault.add_folder("工作")
    e = service.create(data={"title": "阿里云"}, folder_id=f.id)
    assert e.folder_id == f.id


def test_create_unknown_folder_raises(service):
    with pytest.raises(PassbookError):
        service.create(data={"title": "x"}, folder_id="no-such-folder")


def test_create_unknown_type_raises(service):
    with pytest.raises(ValueError):
        service.create(entry_type="bogus", data={"title": "x"})


def test_update_partial_merge(service):
    e = service.create(data={"title": "GitHub", "username": "old"})
    service.update(e.id, {"username": "new", "url": "https://github.com"})
    e2 = service.get(e.id)
    assert e2.data["title"] == "GitHub"      # 未传的字段保留
    assert e2.data["username"] == "new"
    assert e2.data["url"] == "https://github.com"


def test_update_cannot_blank_title(service):
    e = service.create(data={"title": "GitHub"})
    with pytest.raises(PassbookError):
        service.update(e.id, {"title": "   "})


def test_set_folder(service):
    f = service.vault.add_folder("个人")
    e = service.create(data={"title": "x"})
    service.set_folder(e.id, f.id)
    assert service.get(e.id).folder_id == f.id
    with pytest.raises(PassbookError):
        service.set_folder(e.id, "no-such")


def test_toggle_favorite(service):
    e = service.create(data={"title": "x"})
    assert service.toggle_favorite(e.id) is True
    assert service.toggle_favorite(e.id) is False


def test_list_and_trash(service):
    e1 = service.create(data={"title": "a"})
    e2 = service.create(data={"title": "b"})
    service.delete(e1.id)
    assert [e.id for e in service.list_entries()] == [e2.id]
    assert [e.id for e in service.list_trash()] == [e1.id]
    service.restore(e1.id)
    assert len(service.list_entries()) == 2
    service.delete(e1.id)
    service.purge(e1.id)
    assert len(service.list_trash()) == 0


def test_search(service):
    service.create(data={"title": "GitHub", "username": "xijisunset"})
    service.create(data={"title": "阿里云", "url": "aliyun.com"})
    assert len(service.search("github")) == 1
    assert len(service.search("aliyun")) == 1
    assert len(service.search("不存在")) == 0


def test_copy_password(service):
    e = service.create(data={"title": "x", "password": "secret123"})
    service.copy_password(e.id, ttl=10)
    assert FakeClipboard.content == "secret123"


def test_copy_password_clears_after_ttl(service):
    e = service.create(data={"title": "x", "password": "secret123"})
    service.copy_password(e.id, ttl=0.1)
    assert FakeClipboard.content == "secret123"
    time.sleep(0.4)
    assert FakeClipboard.content == ""  # 定时清空生效


def test_copy_password_not_cleared_if_changed(service):
    e = service.create(data={"title": "x", "password": "secret123"})
    service.copy_password(e.id, ttl=0.1)
    FakeClipboard.copy("用户自己复制了别的内容")
    time.sleep(0.4)
    assert FakeClipboard.content == "用户自己复制了别的内容"  # 不误清


def test_copy_password_without_password_raises(service):
    e = service.create(data={"title": "无密码"})
    with pytest.raises(PassbookError):
        service.copy_password(e.id)


def test_get_missing_raises(service):
    with pytest.raises(KeyError):
        service.get("no-such-id")
