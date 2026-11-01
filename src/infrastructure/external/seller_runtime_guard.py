"""Lightweight runtime guard for seller engine interactions.

Tracks consecutive failures that are likely related to auth token or
WebSocket channel issues and auto-pauses dispatch to reduce risk.
Supports auto-resume after a quiet period, optional webhook alerts,
and Playwright browser fallback for recovery.
This is intentionally non-invasive and does not modify vendor code.
"""

import asyncio
import logging
import os
import time
from typing import Any, Callable, Optional

import httpx

from src.infrastructure.external.seller_client import SellerClient, SellerError
from src.infrastructure.external.seller_browser_fallback import SellerBrowserFallback

logger = logging.getLogger(__name__)


class SellerRuntimeGuard:
    """Circuit-breaker style guard around SellerClient."""

    def __init__(
        self,
        seller: Optional[SellerClient] = None,
        failure_threshold: int = 5,
        reset_window_seconds: int = 300,
        auto_resume_seconds: int = 600,
        pause_callback: Optional[Callable[[bool], Any]] = None,
        alert_webhook: Optional[str] = None,
    ):
        self.seller = seller or SellerClient()
        self.failure_threshold = failure_threshold
        self.reset_window_seconds = reset_window_seconds
        self.auto_resume_seconds = auto_resume_seconds
        self.pause_callback = pause_callback
        self.alert_webhook = alert_webhook or os.getenv("SELLER_ALERT_WEBHOOK", "")
        self.browser_fallback = SellerBrowserFallback()

        self._consecutive_failures = 0
        self._last_failure_time = 0.0
        self._paused_by_guard = False
        self._pause_time = 0.0

    def _is_auth_or_channel_error(self, exc: Exception) -> bool:
        """Heuristic: classify errors that are likely token / WS related."""
        if isinstance(exc, SellerError):
            msg = str(exc).lower()
            if exc.status in (401, 403, 429):
                return True
            if any(k in msg for k in ("token", "session", "websocket", "wss", "auth", "login")):
                return True
        return False

    async def _maybe_auto_resume(self):
        if not self._paused_by_guard or not self.pause_callback:
            return
        if time.time() - self._pause_time < self.auto_resume_seconds:
            return
        # Quiet period elapsed; attempt resume
        logger.info("Auto-resume window reached, clearing guard pause")
        self._paused_by_guard = False
        self._consecutive_failures = 0
        try:
            result = self.pause_callback(False)
            if hasattr(result, "__await__"):
                await result
            logger.info("Auto-resume completed")
        except Exception as exc:
            logger.error(f"Auto-resume callback failed: {exc}")

    async def _try_browser_recovery(self):
        """Optional browser-based recovery when paused."""
        if not self.browser_fallback.enabled:
            return False
        logger.info("Attempting browser fallback recovery")
        # Example: try to refresh cookies for a default account context
        cookies = await self.browser_fallback.refresh_cookies_via_browser("default")
        if cookies:
            logger.info("Browser recovery obtained cookies (manual re-import may still be required)")
            # In a full implementation this could update the seller account store
            return True
        return False

    async def _send_alert(self, message: str):
        if not self.alert_webhook:
            return
        payload = {
            "msgtype": "text",
            "text": {"content": f"[ai-goofish-all] {message}"},
            "message": message,
            "timestamp": int(time.time()),
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(self.alert_webhook, json=payload)
            logger.info("Alert webhook sent")
        except Exception as exc:
            logger.warning(f"Alert webhook failed (non-blocking): {exc}")

    def _record_success(self):
        if self._consecutive_failures:
            logger.info("Seller runtime recovered, resetting failure counter")
        self._consecutive_failures = 0
        self._last_failure_time = 0.0

    async def _record_failure(self, exc: Exception):
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
                self._pause_time = now
                if self.pause_callback:
                    try:
                        result = self.pause_callback(True)
                        if hasattr(result, "__await__"):
                            await result
                    except Exception as cb_exc:
                        logger.error(f"Pause callback failed: {cb_exc}")
                # Fire-and-forget alert + optional browser recovery
                asyncio.create_task(self._send_alert(
                    f"卖家引擎连续失败 {self._consecutive_failures} 次，已自动暂停派发。请检查登录态或风控。"
                ))
                asyncio.create_task(self._try_browser_recovery())

    async def request(self, method: str, path: str, payload: Any = None):
        """Guarded request. Call this instead of seller.request when you want protection."""
        await self._maybe_auto_resume()
        try:
            result = await self.seller.request(method, path, payload)
            self._record_success()
            return result
        except Exception as exc:
            await self._record_failure(exc)
            raise

    def status(self) -> dict:
        return {
            "consecutive_failures": self._consecutive_failures,
            "paused_by_guard": self._paused_by_guard,
            "threshold": self.failure_threshold,
            "auto_resume_seconds": self.auto_resume_seconds,
            "last_failure_ago_seconds": (
                int(time.time() - self._last_failure_time) if self._last_failure_time else None
            ),
            "paused_ago_seconds": (
                int(time.time() - self._pause_time) if self._pause_time else None
            ),
            "alert_webhook_configured": bool(self.alert_webhook),
            "browser_fallback_enabled": self.browser_fallback.enabled,
        }
