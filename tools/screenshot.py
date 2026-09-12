"""用 Playwright 打开本地界面，点一次"生成报告"，截一张完整页面图。

用途：README 里的产品截图。手动截图总是截不全（页面比屏幕长），
用脚本跑一遍顺便也验证了整条链路在真实浏览器里是否正常。

用法（先确保 8502 端口的 Streamlit 和本地模型服务都在跑）：
    python tools/screenshot.py
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8502/"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshot.png"


def launch(p):
    """优先用系统自带的 Edge，省掉下载 Chromium 那一百多兆。"""
    last_err = None
    for kwargs in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
        try:
            return p.chromium.launch(headless=True, **kwargs)
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"没能启动任何浏览器：{last_err}")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = launch(p)
        # 视口故意开得很高：Streamlit 的主内容区是个内部滚动容器，
        # 用 full_page 截不到被滚出去的部分，只能把视口撑大到装下整页。
        page = browser.new_page(
            viewport={"width": 1280, "height": 2600},
            device_scale_factor=1,
        )
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_selector("text=ShopMind", timeout=60_000)
        page.wait_for_timeout(3_000)  # 等图表渲染完

        page.get_by_role("button", name="生成报告").click()
        print("已点击生成报告，等模型输出…")
        page.wait_for_selector("text=下载报告", timeout=300_000)
        page.wait_for_timeout(2_000)

        # 点完按钮后页面会滚到报告位置，截图前把所有滚动容器复位
        page.evaluate(
            "() => document.querySelectorAll('*').forEach("
            "el => { if (el.scrollTop) el.scrollTop = 0; })"
        )
        page.wait_for_timeout(1_000)

        page.screenshot(path=str(OUT), full_page=False)
        print("已保存:", OUT)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
