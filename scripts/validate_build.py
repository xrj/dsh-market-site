#!/usr/bin/env python3
"""在部署前校验数据、静态文件和 Sitemap，阻止异常结果覆盖线上版本。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


def fail(message: str) -> "NoReturn":
    """统一输出失败原因并终止工作流。"""
    print(f"校验失败：{message}", file=sys.stderr)
    raise SystemExit(1)


def read_json(path: Path) -> dict[str, Any]:
    """读取 JSON 文件并确保顶层是对象。"""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"无法读取 JSON：{path}: {exc}")
    if not isinstance(value, dict):
        fail(f"JSON 顶层不是对象：{path}")
    return value


def main() -> int:
    """执行部署前的完整静态产物检查。"""
    parser = argparse.ArgumentParser(description="校验 DSH 集市构建产物")
    parser.add_argument("--site-dir", type=Path, default=Path("site"), help="静态站目录")
    parser.add_argument("--before", type=Path, help="构建前目录快照")
    args = parser.parse_args()

    data = read_json(args.site_dir / "data.json")
    report = read_json(args.site_dir / "update-report.json")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        fail("目录条目为空")
    if int(data.get("count") or 0) != len(items):
        fail("count 与 items 数量不一致")
    fetch = report.get("fetch") or {}
    if fetch.get("mode") != "github-merge" or int(fetch.get("fetchedCount") or 0) <= 0:
        fail("没有得到有效的 GitHub 抓取结果")

    full_names = [str(item.get("fullName") or "") for item in items]
    slugs = [str(item.get("detailSlug") or "") for item in items]
    if any(not name or "/" not in name for name in full_names):
        fail("存在缺少 fullName 的条目")
    if len(set(full_names)) != len(full_names):
        fail("存在重复的 GitHub 仓库")
    if len(set(slugs)) != len(slugs) or any(not slug for slug in slugs):
        fail("详情页 slug 为空或重复")

    # 防止数据源异常时把目录突然清空或膨胀到明显不合理的规模。
    if args.before and args.before.exists():
        previous = read_json(args.before)
        previous_count = int(previous.get("count") or len(previous.get("items") or []))
        current_count = len(items)
        if previous_count > 0 and current_count < max(100, int(previous_count * 0.7)):
            fail(f"目录数量从 {previous_count} 大幅下降到 {current_count}")
        if previous_count > 0 and current_count > previous_count * 3:
            fail(f"目录数量从 {previous_count} 异常增长到 {current_count}")

    required_files = ["index.html", "robots.txt", "sitemap.xml", "google16318b32d840ca11.html"]
    for filename in required_files:
        path = args.site_dir / filename
        if not path.exists() or path.stat().st_size == 0:
            fail(f"缺少静态文件：{path}")

    try:
        tree = ElementTree.parse(args.site_dir / "sitemap.xml")
    except (OSError, ElementTree.ParseError) as exc:
        fail(f"Sitemap XML 无法解析：{exc}")
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
    locs = tree.findall(f".//{namespace}")
    if len(locs) != len(items) + 1:
        fail(f"Sitemap URL 数量为 {len(locs)}，预期 {len(items) + 1}")
    if any(not (node.text or "").startswith("https://dsh-market.pages.dev/") for node in locs):
        fail("Sitemap 出现非本站 URL")

    generated = str(report.get("generatedAt") or "")
    try:
        timestamp = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours > 48:
            fail("更新报告时间过旧")
    except ValueError:
        fail("更新报告时间格式不正确")

    print(f"构建校验通过：{len(items)} 个项目，{len(locs)} 个 Sitemap URL，抓取 {fetch.get('fetchedCount')} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
