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


def test_dispatch_pause_is_persistent_and_blocks_real_relist(tmp_path, monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(Path('vendor/xianyu-auto-reply-fix').resolve()))
    monkeypatch.setenv('ALL_DISPATCH_PAUSE_FILE', str(tmp_path / 'pause'))
    from all_runtime import set_dispatch_paused, dispatch_paused
    from auto_relist_task import AutoRelistService
    import asyncio
    set_dispatch_paused(True)
    assert dispatch_paused()
    # The real entry must return before touching seller DB or account sessions.
    service = object.__new__(AutoRelistService)
    assert asyncio.run(service.process({})) == 'paused'
    set_dispatch_paused(False)
    assert not dispatch_paused()
