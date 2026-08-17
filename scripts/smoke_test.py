#!/usr/bin/env python3
"""部署后检查公开入口，只读取页面，不写入线上服务。"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def fetch(url: str) -> tuple[int, str]:
    """请求一个公开页面并返回状态码和少量正文。"""
    request = urllib.request.Request(url, headers={"User-Agent": "dsh-market-deploy-check/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read(200_000).decode("utf-8", errors="replace")


def main() -> int:
    """检查首页、robots、Sitemap 和一张详情页。"""
    parser = argparse.ArgumentParser(description="检查 DSH 集市线上入口")
    parser.add_argument("--site-url", default="https://dsh-market.pages.dev", help="线上站点地址")
    parser.add_argument("--data", type=Path, default=Path("site/data.json"), help="构建后的目录数据")
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    first = (data.get("items") or [{}])[0]
    paths = ["/", "/robots.txt", "/sitemap.xml", f"/plugins/{first.get('detailSlug', '')}/"]
    failures = []
    for path in paths:
        url = args.site_url.rstrip("/") + path
        last_error = ""
        for attempt in range(3):
            try:
                status, body = fetch(url)
                if status == 200 and body:
                    print(f"HTTP 200 {path}")
                    break
                last_error = f"HTTP {status}"
            except (OSError, urllib.error.URLError) as exc:
                last_error = str(exc)
            if attempt < 2:
                time.sleep(3)
        else:
            failures.append(f"{path}: {last_error}")
    if failures:
        raise SystemExit("线上检查失败：" + "；".join(failures))
    print("线上入口检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
