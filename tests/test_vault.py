"""Vault 领域模型测试：CRUD / 软删回收站 / 搜索 / 文件夹 / 序列化。"""

import pytest

from passbook.core.entry import Entry
from passbook.core.vault import Vault


def _entry(**kw) -> Entry:
    base = dict(type="login", data={"title": "哔哩哔哩", "username": "汐霁", "url": "bilibili.com", "password": "x"})
    base.update(kw)
    return Entry(**base)


# ---------- 条目 CRUD ----------
def test_add_and_get_entry():
    v = Vault()
    e = _entry()
    v.add_entry(e)
    assert v.get_entry(e.id) is e
    assert v.get_entry("nonexistent") is None


def test_add_duplicate_id_rejected():
    v = Vault()
    e = _entry()
    v.add_entry(e)
    with pytest.raises(ValueError):
        v.add_entry(Entry(id=e.id))


def test_update_entry_replaces_and_touches():
    v = Vault()
    e = _entry()
    v.add_entry(e)
    e2 = Entry(id=e.id, data={"title": "新标题", "username": "u", "password": "p"})
    v.update_entry(e2)
    assert v.get_entry(e.id).data["title"] == "新标题"
    assert v.get_entry(e.id).updated_at >= e2.updated_at


def test_update_missing_entry_raises():
    v = Vault()
    with pytest.raises(KeyError):
        v.update_entry(_entry())


# ---------- 软删 / 回收站 ----------
def test_soft_delete_moves_to_trash():
    v = Vault()
    e = _entry()
    v.add_entry(e)
    v.soft_delete(e.id)
    assert e.deleted_at is not None
    assert e.id not in [x.id for x in v.list_active()]
    assert e.id in [x.id for x in v.list_trash()]


def test_restore_brings_back():
    v = Vault()
    e = _entry()
    v.add_entry(e)
    v.soft_delete(e.id)
    v.restore(e.id)
    assert e.deleted_at is None
    assert e.id in [x.id for x in v.list_active()]


def test_purge_removes_forever():
    v = Vault()
    e = _entry()
    v.add_entry(e)
    v.soft_delete(e.id)
    v.purge(e.id)
    assert v.get_entry(e.id) is None


def test_purge_trash_empties_only_trash():
    v = Vault()
    a, b = _entry(), _entry()
    v.add_entry(a)
    v.add_entry(b)
    v.soft_delete(a.id)
    assert v.purge_trash() == 1
    assert v.get_entry(a.id) is None
    assert v.get_entry(b.id) is not None


# ---------- 搜索 ----------
def test_search_matches_title_username_url_ci():
    v = Vault()
    v.add_entry(_entry(data={"title": "哔哩哔哩", "username": "汐霁SUNSET", "url": "bilibili.com", "password": "x"}))
    v.add_entry(_entry(data={"title": "GitHub", "username": "xijisunset", "url": "github.com", "password": "x"}))
    assert len(v.search("BILIBILI")) == 1
    assert len(v.search("xijisunset")) == 1
    assert len(v.search("哔哩")) == 1
    assert len(v.search("github.com")) == 1
    assert v.search("") == []


def test_search_excludes_trash_by_default():
    v = Vault()
    e = _entry(data={"title": "抖音", "username": "a", "url": "douyin.com", "password": "x"})
    v.add_entry(e)
    v.soft_delete(e.id)
    assert v.search("抖音") == []
    assert len(v.search("抖音", include_trash=True)) == 1


# ---------- 文件夹 ----------
def test_folder_crud():
    v = Vault()
    f = v.add_folder("工作")
    assert v.get_folder(f.id).name == "工作"
    v.rename_folder(f.id, "工作区")
    assert v.get_folder(f.id).name == "工作区"


def test_add_empty_folder_name_rejected():
    v = Vault()
    with pytest.raises(ValueError):
        v.add_folder("   ")


def test_delete_folder_unlinks_entries():
    v = Vault()
    f = v.add_folder("娱乐")
    e = _entry(folder_id=f.id)
    v.add_entry(e)
    v.delete_folder(f.id)
    assert v.get_folder(f.id) is None
    assert e.folder_id is None  # 回退到未分类，条目不丢


def test_list_active_filters_by_folder():
    v = Vault()
    f = v.add_folder("A")
    v.add_entry(_entry(folder_id=f.id))
    v.add_entry(_entry())
    assert len(v.list_active(folder_id=f.id)) == 1


# ---------- 序列化 ----------
def test_to_from_dict_roundtrip():
    v = Vault()
    f = v.add_folder("财务")
    e = v.add_entry(_entry(folder_id=f.id, favorite=True))
    v.soft_delete(v.add_entry(_entry()).id)

    v2 = Vault.from_dict(v.to_dict())
    assert len(v2.entries) == 2
    assert len(v2.folders) == 1
    got = v2.get_entry(e.id)
    assert got.favorite is True
    assert got.data["title"] == "哔哩哔哩"
    assert len(v2.list_trash()) == 1
    assert len(v2.list_active()) == 1


def test_from_dict_rejects_newer_version():
    with pytest.raises(ValueError):
        Vault.from_dict({"format_version": 999, "folders": [], "entries": []})


def test_invalid_entry_type_rejected():
    with pytest.raises(ValueError):
        Entry(type="hack", data={})
