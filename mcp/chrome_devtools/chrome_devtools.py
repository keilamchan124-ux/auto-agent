# mcp/chrome_devtools/chrome_devtools.py

from playwright.sync_api import sync_playwright, Browser, Page
from typing import Optional
import os

class ChromeDevToolsMCP:
    """
    Chrome DevTools MCP - 負責瀏覽器操作與除錯
    """

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.is_launched = False

    def launch(self, headless: bool = True):
        """啟動瀏覽器"""
        if self.is_launched:
            return

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.page = self.browser.new_page()
        self.is_launched = True
        print("✅ Chrome DevTools MCP 已啟動")

    def goto(self, url: str):
        """前往指定網址"""
        if not self.page:
            raise Exception("請先呼叫 launch() 啟動瀏覽器")
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")

    def screenshot(self, path: str = "screenshot.png", full_page: bool = True):
        """截取目前頁面"""
        if not self.page:
            raise Exception("瀏覽器尚未啟動")
        self.page.screenshot(path=path, full_page=full_page)
        return path

    def get_page_content(self) -> str:
        """取得目前頁面的 HTML 內容"""
        if not self.page:
            raise Exception("瀏覽器尚未啟動")
        return self.page.content()

    def execute_js(self, script: str):
        """執行 JavaScript 程式碼"""
        if not self.page:
            raise Exception("瀏覽器尚未啟動")
        return self.page.evaluate(script)

    def get_console_logs(self):
        """取得 Console 日誌（需自行實作監聽）"""
        # 可擴充功能
        pass

    def close(self):
        """關閉瀏覽器"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        self.is_launched = False
        print("✅ Chrome DevTools MCP 已關閉")