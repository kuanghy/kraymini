import pytest
from pathlib import Path


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def minimal_config_toml():
    return '[[subscriptions]]\nurl = "https://example.com/sub"\n'


@pytest.fixture
def write_config(tmp_path):
    def _write(content: str, filename: str = "config.toml") -> Path:
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        return p
    return _write
