import asyncio

from src.failure_guard import FailureGuard
from src import scraper


def test_detected_access_failure_opens_existing_guard_immediately(monkeypatch, tmp_path):
    guard = FailureGuard(path=str(tmp_path / "guard.json"))
    monkeypatch.setattr(scraper, "FAILURE_GUARD", guard)

    async def discard_notification(*args, **kwargs):
        pass

    monkeypatch.setattr(scraper, "send_ntfy_notification", discard_notification)
    asyncio.run(scraper._notify_task_failure(
        {"task_name": "risk"}, "FAIL_SYS_USER_VALIDATE", cookie_path=None,
        pause_immediately=True,
    ))
    assert guard.should_skip_start("risk").skip is True
    assert guard.should_skip_start("risk").consecutive_failures == 1


def test_ordinary_error_keeps_existing_failure_threshold(monkeypatch, tmp_path):
    guard = FailureGuard(path=str(tmp_path / "guard.json"))
    monkeypatch.setattr(scraper, "FAILURE_GUARD", guard)
    asyncio.run(scraper._notify_task_failure(
        {"task_name": "network"}, "temporary timeout", cookie_path=None,
    ))
    assert guard.should_skip_start("network").skip is False
    assert guard.should_skip_start("network").consecutive_failures == 1


def test_market_response_rejects_access_restrictions_before_parsing():
    import pytest

    class Response:
        def __init__(self, status, payload):
            self.status = status
            self.ok = status < 400
            self.payload = payload

        async def json(self):
            return self.payload

    for status, payload in [
        (403, {}), (429, {}),
        (200, {"ret": ["FAIL_SYS_USER_VALIDATE::验证"]}),
    ]:
        with pytest.raises(scraper.RiskControlError):
            asyncio.run(scraper._read_market_response(Response(status, payload)))

    payload = {"ret": ["SUCCESS::成功"], "data": {"resultList": []}}
    assert asyncio.run(scraper._read_market_response(Response(200, payload))) == payload
