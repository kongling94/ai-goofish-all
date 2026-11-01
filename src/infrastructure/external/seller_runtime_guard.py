"""Lightweight runtime guard for seller engine interactions.

Tracks consecutive failures that are likely related to auth token or
WebSocket channel issues and auto-pauses dispatch to reduce risk.
This is intentionally non-invasive and does not modify vendor code.
"""

import logging
import time
from typing import Any, Callable, Optional

from src.infrastructure.external.seller_client import SellerClient, SellerError

logger = logging.getLogger(__name__)


class SellerRuntimeGuard:
    """Circuit-breaker style guard around SellerClient."""

    def __init__(
        self,
        seller: Optional[SellerClient] = None,
        failure_threshold: int = 5,
        reset_window_seconds: int = 300,
        pause_callback: Optional[Callable[[bool], Any]] = None,
    ):
        self.seller = seller or SellerClient()
        self.failure_threshold = failure_threshold
        self.reset_window_seconds = reset_window_seconds
        self.pause_callback = pause_callback

        self._consecutive_failures = 0
        self._last_failure_time = 0.0
        self._paused_by_guard = False

    def _is_auth_or_channel_error(self, exc: Exception) -> bool:
        """Heuristic: classify errors that are likely token / WS related."""
        if isinstance(exc, SellerError):
            # 401/403/429 or messages that mention token / session / websocket
            msg = str(exc).lower()
            if exc.status in (401, 403, 429):
                return True
            if any(k in msg for k in ("token", "session", "websocket", "wss", "auth", "login")):
                return True
        return False

    def _record_success(self):
        if self._consecutive_failures:
            logger.info("Seller runtime recovered, resetting failure counter")
        self._consecutive_failures = 0
        self._last_failure_time = 0.0
        if self._paused_by_guard and self.pause_callback:
            # optional auto-resume can be added later; currently leave paused
            pass

    def _record_failure(self, exc: Exception):
        now = time.time()
        if now - self._last_failure_time > self.reset_window_seconds:
            self._consecutive_failures = 0

        if self._is_auth_or_channel_error(exc):
            self._consecutive_failures += 1
            self._last_failure_time = now
            logger.warning(
                f"Seller auth/channel failure #{self._consecutive_failures}: {exc}"
            )
            if self._consecutive_failures >= self.failure_threshold and not self._paused_by_guard:
                logger.error(
                    f"Failure threshold ({self.failure_threshold}) reached, auto-pausing dispatch"
                )
                self._paused_by_guard = True
                if self.pause_callback:
                    try:
                        # pause_callback is expected to be async-aware or sync
                        result = self.pause_callback(True)
                        if hasattr(result, "__await__"):
                            # fire-and-forget if caller didn't await; better to await in real usage
                            pass
                    except Exception as cb_exc:
                        logger.error(f"Pause callback failed: {cb_exc}")

    async def request(self, method: str, path: str, payload: Any = None):
        """Guarded request. Call this instead of seller.request when you want protection."""
        try:
            result = await self.seller.request(method, path, payload)
            self._record_success()
            return result
        except Exception as exc:
            self._record_failure(exc)
            raise

    def status(self) -> dict:
        return {
            "consecutive_failures": self._consecutive_failures,
            "paused_by_guard": self._paused_by_guard,
            "threshold": self.failure_threshold,
            "last_failure_ago_seconds": (
                int(time.time() - self._last_failure_time) if self._last_failure_time else None
            ),
        }
