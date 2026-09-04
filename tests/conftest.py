"""pytest 共享夹具。

测试统一用低 KDF 参数（1MiB / t=1 / p=1），Argon2id 仍可正常派生，
只是变快数倍，保证单测秒级跑完。
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from passbook.crypto.kdf import KdfParams  # noqa: E402

PASSWORD = "测试主密码-Admin@2026"
PAYLOAD = '{"title": "哔哩哔哩", "username": "汐霁SUNSET", "password": "s3cret!"}'


@pytest.fixture
def fast_params() -> KdfParams:
    return KdfParams(memory_mib=1, iterations=1, parallelism=1)


@pytest.fixture
def vault_path(tmp_path) -> str:
    return str(tmp_path / "test.pbk")


@pytest.fixture(scope="session")
def qapp():
    """Qt 应用单例。PySide6 未安装时自动跳过依赖它的测试。"""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app
