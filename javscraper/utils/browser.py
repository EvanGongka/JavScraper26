from __future__ import annotations

import platform

try:
    import browser_cookie3
except ImportError:
    browser_cookie3 = None


def load_browser_cookies(domains: list[str]) -> dict[str, str]:
    if browser_cookie3 is None:
        return {}

    loaders = [
        getattr(browser_cookie3, "chrome", None),
        getattr(browser_cookie3, "chromium", None),
        getattr(browser_cookie3, "edge", None),
        getattr(browser_cookie3, "brave", None),
        getattr(browser_cookie3, "vivaldi", None),
    ]

    cookies: dict[str, str] = {}
    for loader in loaders:
        if loader is None:
            continue
        for domain in domains:
            try:
                jar = loader(domain_name=domain)
            except Exception:
                continue
            for item in jar:
                cookies[item.name] = item.value
        if cookies:
            break
    return cookies


def get_javdb_cookie_status() -> dict[str, str | bool]:
    cookies = load_browser_cookies(["javdb.com"])
    required_keys = {"_jdb_session", "remember_me_token", "cf_clearance"}
    if not cookies:
        system = platform.system().lower()
        if system == "windows":
            return {
                "available": False,
                "reason": "Windows 未读取到 javdb.com Cookie，默认不勾选",
            }
        return {
            "available": False,
            "reason": "未读取到 javdb.com Cookie，默认不勾选",
        }

    if any(key in cookies for key in required_keys):
        return {
            "available": True,
            "reason": "已检测到浏览器登录态",
        }

    return {
        "available": False,
        "reason": "浏览器中未找到有效登录态，默认不勾选",
    }
