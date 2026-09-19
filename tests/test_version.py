"""版本号一致性（审计 P3#2 回归）：三处同步，防止发布时再漂移。"""

import re
from pathlib import Path

import passbook

ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_pyproject():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', text, re.M)
    assert m is not None
    assert m.group(1) == passbook.__version__


def test_version_has_changelog_entry():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## v{passbook.__version__}" in changelog
