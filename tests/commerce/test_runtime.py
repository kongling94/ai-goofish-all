import importlib.util
from pathlib import Path
import pytest


def test_seller_preview_gate_is_fail_closed(monkeypatch):
    path = Path('vendor/xianyu-auto-reply-fix/all_runtime.py')
    spec = importlib.util.spec_from_file_location('all_runtime', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv('ALL_EXECUTION_MODE', raising=False)
    assert not module.is_live()
    with pytest.raises(RuntimeError):
        module.require_live()
    monkeypatch.setenv('ALL_EXECUTION_MODE', 'live')
    assert module.is_live()
