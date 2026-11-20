import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from der.api.deps import reset_runtime  # noqa: E402


@pytest.fixture(autouse=True)
def clean_runtime():
    """每个用例前后清空进程内状态，保证互不干扰。"""
    reset_runtime()
    yield
    reset_runtime()
