from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


URL = "http://127.0.0.1:8765/emby-api/v1/health"


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=3) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status != 200:
                print(f"健康检查 HTTP 状态异常: {response.status} body={body[:500]}", file=sys.stderr)
                return 1
            payload = json.loads(body)
            if payload.get("status") != "ok":
                print(f"健康检查状态异常: {body[:500]}", file=sys.stderr)
                return 1
            return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"健康检查 HTTP 错误: {exc.code} body={body[:500]}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"健康检查请求失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
