"""Browser automation fallback for critical seller operations.

Used when reverse-engineered APIs fail repeatedly. Relies on Playwright
(already in project dependencies). Designed as a recovery tool, not a
primary path.
"""

import logging
import os
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class SellerBrowserFallback:
    """Lightweight Playwright-based recovery helpers."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.enabled = os.getenv("SELLER_BROWSER_FALLBACK", "false").lower() in ("1", "true", "yes")

    async def refresh_cookies_via_browser(self, account_id: str, login_url: str = "https://www.goofish.com") -> Optional[str]:
        """Attempt to refresh session cookies by visiting the site.

        Returns new cookies string on success, None otherwise.
        Note: Full login automation is intentionally limited; this mainly
        helps with already-authenticated browser contexts or simple keep-alive.
        """
        if not self.enabled:
            logger.info("Browser fallback disabled (set SELLER_BROWSER_FALLBACK=true to enable)")
            return None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context()
                page = await context.new_page()
                logger.info(f"[{account_id}] Browser fallback: navigating to {login_url}")
                await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                # Simple keep-alive / cookie refresh. Full QR login would require more interaction.
                await page.wait_for_timeout(3000)
                cookies = await context.cookies()
                cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
                await browser.close()
                if cookie_str:
                    logger.info(f"[{account_id}] Browser fallback obtained cookies ({len(cookies)} items)")
                    return cookie_str
                return None
        except Exception as exc:
            logger.error(f"Browser fallback cookie refresh failed: {exc}")
            return None

    async def verify_publish_status(self, item_id: str, account_cookies: Optional[str] = None) -> bool:
        """Best-effort check whether an item appears published by visiting its page."""
        if not self.enabled or not item_id:
            return False
        url = f"https://www.goofish.com/item?id={item_id}"
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context()
                if account_cookies:
                    # Basic cookie injection (simplified)
                    await context.add_cookies([
                        {"name": part.split("=", 1)[0], "value": part.split("=", 1)[1], "domain": ".goofish.com", "path": "/"}
                        for part in account_cookies.split("; ") if "=" in part
                    ])
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                content = await page.content()
                await browser.close()
                # Heuristic: page loaded and not a clear 404/error
                success = "item" in content.lower() or len(content) > 5000
                logger.info(f"Browser verify item {item_id}: {'likely exists' if success else 'uncertain'}")
                return success
        except Exception as exc:
            logger.error(f"Browser verify failed for {item_id}: {exc}")
            return False
