import time
from typing import Dict


def generate_selector(element_info: dict) -> dict:
    """根据元素信息生成 CSS 和 XPath 选择器。"""
    tag = element_info.get("tag", "")
    elem_id = element_info.get("id", "")
    classes = element_info.get("classes", [])

    # CSS
    css_parts = [tag]
    if elem_id:
        css_parts.append(f"#{elem_id}")
    for c in classes[:2]:
        css_parts.append(f".{c}")
    css = "".join(css_parts)

    # XPath
    xpath = f"//{tag}"
    conditions = []
    if elem_id:
        conditions.append(f"@id='{elem_id}'")
    for c in classes[:2]:
        conditions.append(f"contains(@class,'{c}')")
    if conditions:
        xpath += "[" + " and ".join(conditions) + "]"

    return {"css": css, "xpath": xpath}


def pick_selector(url: str) -> Dict[str, str]:
    """启动 Playwright 浏览器，让用户点击元素并返回生成的选择器。

    注意：此函数会阻塞当前线程，建议在 GUI 后台线程中调用。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("未安装 Playwright，请先执行: pip install playwright && playwright install chromium") from e

    result = {"css": "", "xpath": ""}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(url, wait_until="networkidle")

        # 注入选择脚本，点击元素后返回元素信息
        page.evaluate("""
            window._picked = null;
            document.addEventListener('mouseover', function(e) {
                if (window._picked) return;
                e.target.style.outline = '2px solid red';
            }, true);
            document.addEventListener('mouseout', function(e) {
                if (window._picked) return;
                e.target.style.outline = '';
            }, true);
            document.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var el = e.target;
                var info = {
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    classes: Array.from(el.classList),
                    text: el.innerText || ''
                };
                window._picked = info;
            }, true);
        """)

        # 最多等待 5 分钟
        for _ in range(600):
            picked = page.evaluate("window._picked")
            if picked:
                result = generate_selector(picked)
                break
            time.sleep(0.5)

        browser.close()
    return result
