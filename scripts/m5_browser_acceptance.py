"""Desktop and mobile browser acceptance for the complete local product shell."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


def assert_page(page: Page, url: str, screenshot: Path) -> None:
    errors: list[str] = []
    page.on(
        "console", lambda message: errors.append(message.text) if message.type == "error" else None
    )
    page.goto(url, wait_until="networkidle", timeout=30_000)
    create = page.get_by_role("button", name="创建《异环》项目")
    if create.count():
        create.click()
    page.get_by_role("heading", name="异环海外营销工作台").wait_for(timeout=10_000)
    page.locator("#journey-title").wait_for(timeout=10_000)
    page.get_by_role("button", name=re.compile(r"继续下一步|首条营销链路已完成")).wait_for()
    recommended = page.get_by_role("button", name=re.compile("导入异环英文官网首页"))
    if recommended.count():
        recommended.wait_for(timeout=10_000)
        box = recommended.bounding_box()
        if box is None or box["y"] >= page.viewport_size["height"]:
            raise AssertionError("recommended first action is not visible in the initial viewport")
    if page.locator(".journey-details").evaluate("element => element.open"):
        raise AssertionError("diagnostic journey detail should be collapsed by default")
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 2")
    if overflow:
        raise AssertionError("page has horizontal overflow")
    if errors:
        raise AssertionError(f"browser console errors: {errors}")
    page.screenshot(path=str(screenshot), full_page=True)
    page.get_by_role("button", name="账户与团队").click()
    page.get_by_role("heading", name="本机运行诊断").wait_for(timeout=10_000)
    page.get_by_text("运行正常", exact=True).wait_for(timeout=10_000)
    page.get_by_label("恢复项目备份").wait_for(timeout=10_000)
    if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 2"):
        raise AssertionError("account recovery page has horizontal overflow")
    page.screenshot(
        path=str(screenshot.with_name(f"{screenshot.stem}-recovery{screenshot.suffix}")),
        full_page=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--output")
    args = parser.parse_args()
    output = (
        Path(args.output)
        if args.output
        else Path(tempfile.gettempdir()) / "gamecrafter-complete-local-browser"
    )
    output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        desktop = browser.new_page(viewport={"width": 1440, "height": 1000})
        assert_page(desktop, args.url, output / "desktop.png")
        mobile = browser.new_page(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            is_mobile=True,
        )
        assert_page(mobile, args.url, output / "mobile.png")
        browser.close()
    print("Complete local desktop and mobile browser acceptance passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
