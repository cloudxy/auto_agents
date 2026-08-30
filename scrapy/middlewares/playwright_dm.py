"""Playwright 动态渲染下载中间件

当请求标记 meta['render_js'] = True 时，使用 Playwright 渲染页面，
将渲染后的 HTML 注入到 response.body 供后续选择器提取。

资源管理：
- 浏览器进程池（限制并发数，配置 PLAYWRIGHT_MAX_PAGES）
- 每个页面使用独立 context（隔离 Cookie/缓存）
- 渲染完成后关闭 page，复用 browser

约束：
- 仅在请求明确标记 render_js=True 时启用（非默认行为）
- 超时配置 PLAYWRIGHT_TIMEOUT（默认 30s）
- 需要 playwright 已安装（可选依赖，未安装时中间件自动跳过）
"""
import asyncio

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse

from platform_core.logger import get_logger

logger = get_logger("spider")


class PlaywrightMiddleware:
    """Playwright 动态渲染下载中间件

    使用方式：
    1. 请求 meta 设置 render_js=True
    2. 可选设置 wait_for（CSS 选择器，等待元素出现）
    3. 可选设置 wait_timeout（等待超时，默认取 PLAYWRIGHT_TIMEOUT）

    配置（settings.yml / spider custom_settings）：
    - PLAYWRIGHT_ENABLED: bool（默认 False）
    - PLAYWRIGHT_MAX_PAGES: int（最大并发页面数，默认 2）
    - PLAYWRIGHT_TIMEOUT: int（渲染超时秒数，默认 30）
    - PLAYWRIGHT_BROWSER: str（浏览器类型 chromium/firefox/webkit，默认 chromium）
    """

    def __init__(self, max_pages: int = 2, timeout: int = 30, browser_type: str = "chromium"):
        self._max_pages = max_pages
        self._timeout = timeout
        self._browser_type = browser_type
        self._browser = None
        self._playwright = None
        self._semaphore: asyncio.Semaphore | None = None
        self._active_pages = 0

    @classmethod
    def from_crawler(cls, crawler):
        enabled = crawler.settings.getbool("PLAYWRIGHT_ENABLED", False)
        if not enabled:
            raise NotConfigured("PLAYWRIGHT_ENABLED=False")

        try:
            import playwright  # noqa: F401  检查是否安装
        except ImportError:
            raise NotConfigured("playwright 未安装，跳过 PlaywrightMiddleware")

        middleware = cls(
            max_pages=crawler.settings.getint("PLAYWRIGHT_MAX_PAGES", 2),
            timeout=crawler.settings.getint("PLAYWRIGHT_TIMEOUT", 30),
            browser_type=crawler.settings.get("PLAYWRIGHT_BROWSER", "chromium"),
        )
        crawler.signals.connect(middleware._on_spider_closed, signal=signals.spider_closed)
        return middleware

    def _on_spider_closed(self, spider, reason):
        """spider_closed 信号处理：调度异步关闭浏览器"""
        if self._browser is None and self._playwright is None:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._close_browser())
            else:
                loop.run_until_complete(self._close_browser())
        except RuntimeError:
            logger.warning("Playwright 浏览器关闭失败：无可用事件循环")

    async def _close_browser(self):
        """异步关闭浏览器和 playwright 实例"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Playwright 浏览器已关闭")

    async def _ensure_browser(self):
        """懒初始化浏览器（幂等）"""
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            launcher = getattr(self._playwright, self._browser_type)
            self._browser = await launcher.launch(headless=True)
            self._semaphore = asyncio.Semaphore(self._max_pages)
            logger.info(
                "Playwright 浏览器已启动: %s, max_pages=%d",
                self._browser_type,
                self._max_pages,
            )

    async def _render_page(
        self, url: str, wait_for: str | None = None, wait_timeout: int | None = None
    ) -> str:
        """渲染页面并返回 HTML"""
        await self._ensure_browser()
        timeout_ms = (wait_timeout or self._timeout) * 1000

        async with self._semaphore:
            self._active_pages += 1
            context = await self._browser.new_context()
            page = await context.new_page()
            try:
                await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                if wait_for:
                    await page.wait_for_selector(wait_for, timeout=timeout_ms)
                else:
                    await page.wait_for_load_state("networkidle")
                html = await page.content()
                return html
            finally:
                await page.close()
                await context.close()
                self._active_pages -= 1

    def process_request(self, request, spider):
        """同步入口：检查 render_js 标记"""
        if not request.meta.get("render_js"):
            return None
        return self._async_render(request)

    def _async_render(self, request):
        """异步渲染：返回 Deferred 让 Scrapy 异步等待"""
        from twisted.internet.defer import Deferred

        d = Deferred()
        wait_for = request.meta.get("wait_for")
        wait_timeout = request.meta.get("wait_timeout")

        async def _do_render():
            try:
                html = await self._render_page(request.url, wait_for, wait_timeout)
                response = HtmlResponse(
                    url=request.url,
                    request=request,
                    body=html.encode("utf-8"),
                    encoding="utf-8",
                )
                d.callback(response)
            except Exception as e:
                logger.error("Playwright 渲染失败: %s, error=%s", request.url, e)
                d.errback(e)

        asyncio.ensure_future(_do_render())
        return d
