#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSH 插件集市静态构建脚本。

默认从现有快照生成静态站；--fetch 会通过 GitHub CLI 拉取最近更新的
dsh-plugin Topic 仓库，并与本地完整快照合并。抓取失败时 --fetch 直接
返回非零状态，调用方因此不会把旧数据当成新数据部署。
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
TEMPLATES = ROOT / "templates"
RESEARCH = ROOT / "research"
WHALE_IMAGE = ROOT / "鲸鱼图.png"
GOOGLE_VERIFICATION_FILE = ROOT / "google16318b32d840ca11.html"
DEFAULT_SITE_URL = "https://dsh-market.pages.dev"
GITHUB_SEARCH_PAGES = 10

DEFAULT_CATEGORIES = [
    {"id": "interface-theme", "label": "界面与主题", "color": "#3d72a3"},
    {"id": "agent-session", "label": "Agent 与会话", "color": "#143e35"},
    {"id": "development-automation", "label": "开发与自动化", "color": "#de6947"},
    {"id": "files-knowledge", "label": "文件与知识", "color": "#4d6bfe"},
    {"id": "model-connect", "label": "模型与连接", "color": "#8a6fbe"},
    {"id": "messages", "label": "消息与通知", "color": "#5b8c7d"},
    {"id": "security-permission", "label": "安全与权限", "color": "#b74d45"},
    {"id": "runtime-monitor", "label": "运行与监控", "color": "#607d8b"},
    {"id": "application-desktop", "label": "应用与桌面", "color": "#2f6f63"},
    {"id": "plugin-management", "label": "插件发现与管理", "color": "#6674a8"},
    {"id": "life-entertainment", "label": "生活与娱乐", "color": "#bd6f83"},
    {"id": "tutorials", "label": "教程与资料", "color": "#7a8f4c"},
]

DEFAULT_TYPES = [
    {"id": "plugin", "label": "插件"},
    {"id": "skill", "label": "技能"},
    {"id": "collection", "label": "插件合集"},
    {"id": "external-integration", "label": "外部接入"},
    {"id": "standalone-app", "label": "独立应用"},
    {"id": "support-service", "label": "配套服务"},
    {"id": "plugin-directory", "label": "插件集市"},
]

CATEGORY_LABELS = {entry["id"]: entry["label"] for entry in DEFAULT_CATEGORIES}
TYPE_LABELS = {entry["id"]: entry["label"] for entry in DEFAULT_TYPES}

CATEGORY_KEYWORDS = {
    "security-permission": (
        "security", "sandbox", "permission", "audit", "secret", "policy", "auth", "guardrail", "privacy", "redaction", "provenance", "安全", "权限", "审计", "沙盒"
    ),
    "plugin-management": (
        "marketplace", "plugin-manager", "plugin store", "plugin-store", "registry", "directory", "catalog", "awesome-list", "plugin-list", "plugins-list", "installer", "find-plugin", "plugin hub", "插件市场", "插件管理", "插件目录", "插件安装", "索引"
    ),
    "application-desktop": (
        "electron", "wails", "pwa", "tui", "launcher", "desktop app", "desktop client", "web app", "application", "client", "portable app", "独立应用", "桌面端", "客户端", "应用", "启动器"
    ),
    "messages": (
        "message", "telegram", "discord", "slack", "qq-bot", "wechat-bot", "weixin-bot", "notification", "email", "lark", "feishu", "interconnect", "webhook", "bot", "channel", "消息", "通知", "飞书", "邮件", "机器人"
    ),
    "model-connect": (
        "model", "mcp", "llm", "openai", "anthropic", "gemini", "qwen", "glm", "provider", "oauth", "codex", "vlm", "model-router", "模型", "连接", "接口"
    ),
    "files-knowledge": (
        "file", "data", "ocr", "image", "vision", "database", "document", "pdf", "csv", "markdown", "knowledge", "browser", "paste", "upload", "文件", "图片", "视觉", "文档", "知识", "笔记"
    ),
    "agent-session": (
        "agent", "session", "memory", "conversation", "team", "workflow", "subagent", "orchestration", "prompt", "rewind", "task", "会话", "记忆", "工作流", "子代理", "提示词"
    ),
    "development-automation": (
        "developer", "development", "code", "coding", "vscode", "cli", "terminal", "debug", "test", "git", "bash", "shell", "automation", "tool", "build", "开发", "代码", "终端", "自动化", "工具"
    ),
    "runtime-monitor": (
        "deploy", "docker", "server", "ops", "monitor", "metric", "billing", "token", "gpu", "runtime", "health", "usage", "balance", "cost", "performance", "部署", "监控", "费用", "余额", "运行"
    ),
    "life-entertainment": (
        "game", "music", "voice", "tts", "calendar", "pet", "video", "life", "wallpaper", "rpg", "tavern", "小游戏", "游戏", "音乐", "桌宠", "壁纸", "娱乐"
    ),
    "tutorials": (
        "research", "learn", "study", "paper", "handbook", "tutorial", "guide", "education", "教程", "手册", "学习", "研究", "资料"
    ),
    "interface-theme": (
        "web-ui", "webui", "sidebar", "skin", "theme", "visual", "gui", "layout", "appearance", "panel", "button", "drag", "rotator", "turn-status", "status-bar", "statusbar", "status label", "widget", "hud", "interface", "界面", "侧边栏", "皮肤", "主题", "外观", "状态栏", "浮窗", "面板"
    ),
}


class FetchError(RuntimeError):
    """GitHub 数据更新失败时抛出，避免调用方继续部署。"""


def clean_text(value: Any, limit: int | None = None) -> str:
    """压缩描述中的无意义空白，并限制静态页面中的文本体积。"""
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def safe_url(value: Any) -> str | None:
    """仅保留可公开打开的 HTTP(S) 链接，避免把仓库数据直接当作可执行地址。"""
    text = clean_text(value)
    if not text:
        return None
    parsed = urllib.parse.urlparse(text)
    return text if parsed.scheme in {"http", "https"} else None


def to_int(value: Any) -> int:
    """把 GitHub API 与旧快照里的数字字段统一成非负整数。"""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def bool_value(value: Any) -> bool:
    """兼容旧快照的布尔值和文本布尔值。"""
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def read_json(path: Path) -> dict[str, Any] | None:
    """读取 JSON 快照；无文件或文件损坏时交由上层决定是否回退。"""
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def write_text_atomic(path: Path, content: str) -> None:
    """先写同目录临时文件，再原子替换，降低日更中断导致半个文件上线的风险。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def write_json_atomic(path: Path, value: Any) -> None:
    """以 UTF-8 无 BOM 写出紧凑 JSON。"""
    content = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    write_text_atomic(path, content)


def extract_script_json(source: str, script_id: str) -> Any:
    """从目标站快照的 JSON script 标签提取数据。"""
    pattern = re.compile(
        rf'<script\s+id="{re.escape(script_id)}"\s+type="application/json">(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def load_target_snapshot() -> dict[str, Any] | None:
    """读取已有的竞品快照，作为全量目录的稳定基线。"""
    target = RESEARCH / "target.html"
    if not target.exists():
        return None
    try:
        source = target.read_text(encoding="utf-8")
    except OSError:
        return None
    items = extract_script_json(source, "catalog-data")
    if not isinstance(items, list):
        return None
    return {
        "items": items,
        "categories": extract_script_json(source, "category-data"),
        "types": extract_script_json(source, "type-data"),
        "curatedOrder": extract_script_json(source, "curated-data"),
    }


def pick_value(raw: dict[str, Any], existing: dict[str, Any], key: str) -> Any:
    """新数据缺字段时保留旧快照中仍可用的字段。"""
    return raw[key] if key in raw and raw[key] is not None else existing.get(key)


def normalise_owner(raw: dict[str, Any], existing: dict[str, Any], full_name: str) -> dict[str, str]:
    """兼容 GitHub API、旧目录和手工快照中的 owner 结构。"""
    candidate = raw.get("owner")
    previous = existing.get("owner")
    login = ""
    avatar_url = ""
    for value in (candidate, previous):
        if isinstance(value, dict):
            login = login or clean_text(value.get("login"))
            avatar_url = avatar_url or clean_text(value.get("avatarUrl") or value.get("avatar_url"))
        elif isinstance(value, str):
            login = login or clean_text(value)
    login = login or clean_text(raw.get("owner_login")) or full_name.split("/", 1)[0]
    avatar_url = avatar_url or clean_text(raw.get("owner_avatar_url"))
    result = {"login": login}
    if safe_url(avatar_url):
        result["avatarUrl"] = avatar_url
    return result


def has_keyword(haystack: str, keywords: tuple[str, ...]) -> bool:
    """检查项目文本是否命中分类词，避免 file 误命中 profile 这类英文子串。"""
    for keyword in keywords:
        candidate = keyword.lower()
        if any(ord(char) > 127 for char in candidate):
            if candidate in haystack:
                return True
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])"
        if re.search(pattern, haystack):
            return True
    return False


def classify_type(name: str, description: str, topics: list[str]) -> str:
    """根据项目形态生成用户看得懂的类型，无法确定时按普通插件处理。"""
    haystack = " ".join([name, description, *topics]).lower()
    if has_keyword(haystack, ("skill", "skills", "agent-skill", "agent-skills", "技能")):
        return "skill"
    if has_keyword(haystack, ("awesome", "collection", "plugin-list", "plugins-list", "curated", "合集")):
        return "collection"
    if has_keyword(
        haystack,
        ("directory", "catalog", "marketplace", "registry", "plugin-manager", "plugin-store", "plugin hub", "installer", "目录", "市场", "管理器"),
    ):
        return "plugin-directory"
    if has_keyword(
        haystack,
        ("channel", "telegram", "discord", "slack", "qq-bot", "wechat-bot", "weixin-bot", "lark", "feishu", "email", "webhook", "bot", "bridge", "connector", "外部接入", "机器人"),
    ):
        return "external-integration"
    if has_keyword(
        haystack,
        ("electron", "wails", "pwa", "tui", "launcher", "desktop app", "desktop client", "web app", "application", "client", "portable app", "独立应用", "桌面端", "客户端", "启动器"),
    ):
        return "standalone-app"
    if has_keyword(
        haystack,
        ("infrastructure", "infra", "runtime", "server", "sandbox", "sidecar", "daemon", "service", "worker", "backend", "gateway", "后台服务", "运行环境"),
    ):
        return "support-service"
    return "plugin"


def classify_category(name: str, description: str, topics: list[str], project_type: str = "plugin") -> str:
    """按用户要解决的问题分类，并让旧快照在日更时重新归类。"""
    haystack = " ".join([name, description, *topics]).lower()
    if project_type in {"collection", "plugin-directory"} or has_keyword(haystack, CATEGORY_KEYWORDS["plugin-management"]):
        return "plugin-management"
    if project_type == "standalone-app":
        return "application-desktop"
    for category_id in (
        "security-permission",
        "messages",
        "model-connect",
        "life-entertainment",
        "interface-theme",
        "files-knowledge",
        "agent-session",
        "development-automation",
        "runtime-monitor",
        "tutorials",
    ):
        if has_keyword(haystack, CATEGORY_KEYWORDS[category_id]):
            return category_id
    if has_keyword(haystack, CATEGORY_KEYWORDS["application-desktop"]):
        return "application-desktop"
    if project_type == "external-integration":
        return "messages"
    if project_type == "support-service":
        return "runtime-monitor"
    if project_type == "skill":
        return "agent-session"
    # 目录信息不足时仍放进一个明确的工作类，前台不再出现“其他”。
    return "development-automation"


def normalise_item(raw: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """把 API 返回和旧快照转换成站点统一的数据结构。"""
    existing = existing or {}
    full_name = clean_text(
        raw.get("full_name")
        or raw.get("fullName")
        or existing.get("fullName")
        or raw.get("name")
        or existing.get("name")
    )
    if not full_name:
        return None
    name = clean_text(raw.get("name") or existing.get("name") or full_name.rsplit("/", 1)[-1])
    description = clean_text(raw.get("description") or existing.get("description"), 600)
    raw_topics = raw.get("topics") if isinstance(raw.get("topics"), list) else existing.get("topics", [])
    topics = [clean_text(topic, 80).lower() for topic in raw_topics if clean_text(topic, 80)]
    # 每次构建都重新计算分类，避免旧快照把大量项目永久锁在“其他/待识别”。
    type_id = classify_type(full_name, description, topics)
    category = classify_category(full_name, description, topics, type_id)
    license_value = raw.get("license")
    if isinstance(license_value, dict):
        license_value = license_value.get("spdx_id") or license_value.get("spdxId") or license_value.get("key")
    if license_value is None:
        license_value = existing.get("license")
    url = safe_url(raw.get("html_url") or raw.get("url") or existing.get("url"))
    homepage = safe_url(raw.get("homepage") or existing.get("homepage"))
    featured_source = pick_value(raw, existing, "featured")
    verified_source = pick_value(raw, existing, "verified")
    return {
        "slug": str(raw.get("id") or raw.get("slug") or existing.get("slug") or full_name),
        "name": name,
        "fullName": full_name,
        "description": description,
        "url": url,
        "homepage": homepage,
        "owner": normalise_owner(raw, existing, full_name),
        "topics": topics,
        "language": clean_text(raw.get("language") or existing.get("language"), 80) or None,
        "license": clean_text(license_value, 80) or None,
        "stars": to_int(raw.get("stargazers_count") if "stargazers_count" in raw else raw.get("stars", existing.get("stars"))),
        "forks": to_int(raw.get("forks_count") if "forks_count" in raw else raw.get("forks", existing.get("forks"))),
        "openIssues": to_int(raw.get("open_issues_count") if "open_issues_count" in raw else raw.get("openIssues", existing.get("openIssues"))),
        "createdAt": clean_text(raw.get("created_at") or raw.get("createdAt") or existing.get("createdAt"), 40) or None,
        "pushedAt": clean_text(raw.get("pushed_at") or raw.get("pushedAt") or existing.get("pushedAt"), 40) or None,
        "projectType": type_id,
        "category": category,
        "featured": bool_value(featured_source),
        "verified": bool_value(verified_source),
        "archived": bool_value(raw.get("archived") if "archived" in raw else existing.get("archived")),
        "fork": bool_value(raw.get("fork") if "fork" in raw else existing.get("fork")),
    }


def item_key(item: dict[str, Any]) -> str:
    """以仓库全名作为日更合并键，避免 GitHub 数字 ID 缺失时重复收录。"""
    return clean_text(item.get("fullName")).lower()


def detail_slug(full_name: str, fallback: str) -> str:
    """把仓库全名转换为可读、可复现的静态目录名。"""
    slug = re.sub(r"[^a-z0-9]+", "-", full_name.lower()).strip("-")
    return (slug[:96].strip("-") or re.sub(r"[^a-z0-9]+", "-", fallback.lower()).strip("-") or "plugin")


def assign_detail_slugs(items: list[dict[str, Any]]) -> None:
    """处理极少数 slug 冲突，确保每张卡片的详情链接唯一。"""
    used: dict[str, int] = {}
    for item in items:
        base = detail_slug(item["fullName"], item["slug"])
        index = used.get(base, 0)
        used[base] = index + 1
        item["detailSlug"] = base if index == 0 else f"{base}-{index + 1}"


def merge_catalog_items(sources: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """按给定顺序叠加数据源，后面的快照优先保留为最新字段。"""
    merged: dict[str, dict[str, Any]] = {}
    for source in sources:
        for raw in source:
            if not isinstance(raw, dict):
                continue
            candidate_name = clean_text(raw.get("full_name") or raw.get("fullName") or raw.get("name")).lower()
            existing = merged.get(candidate_name, {})
            item = normalise_item(raw, existing)
            if item:
                merged[item_key(item)] = item
    items = sorted(merged.values(), key=lambda item: (item["fullName"].lower(), item["name"].lower()))
    assign_detail_slugs(items)
    return items


def normalise_categories(value: Any) -> list[dict[str, str]]:
    """固定使用当前分类文案，避免旧快照覆盖已经确认的名称。"""
    categories = []
    for default in DEFAULT_CATEGORIES:
        categories.append(
            {
                "id": default["id"],
                "label": default["label"],
                "color": default["color"],
            }
        )
    return categories


def normalise_types(value: Any) -> list[dict[str, str]]:
    """固定使用当前类型文案，避免旧快照恢复过时的可见名称。"""
    return [
        {
            "id": default["id"],
            "label": default["label"],
        }
        for default in DEFAULT_TYPES
    ]


def load_seed_catalog() -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]], list[str]]:
    """组合 target 快照和 site 快照，为抓取模式保留超过 1000 条的旧项目。"""
    target = load_target_snapshot() or {}
    site_data = read_json(SITE / "data.json") or {}
    sources = [target.get("items", []), site_data.get("items", [])]
    items = merge_catalog_items([source for source in sources if isinstance(source, list)])
    categories = normalise_categories(site_data.get("categories") or target.get("categories"))
    types = normalise_types(site_data.get("types") or target.get("types"))
    curated = site_data.get("curatedOrder") or target.get("curatedOrder") or []
    curated = [clean_text(name, 180) for name in curated if clean_text(name, 180)]
    if not items:
        raise FetchError("未找到可用的目录快照。")
    return items, categories, types, curated


def github_api_page(page: int) -> dict[str, Any]:
    """优先通过已登录的 GitHub CLI 请求公开 API，不读取或输出 Token。"""
    query = urllib.parse.urlencode(
        {
            "q": "topic:dsh-plugin",
            "sort": "updated",
            "order": "desc",
            "per_page": 100,
            "page": page,
        }
    )
    endpoint = f"/search/repositories?{query}"
    if shutil.which("gh"):
        result = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github+json", endpoint],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode == 0:
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError as error:
                raise FetchError("GitHub CLI 返回了无法解析的数据。") from error
            return payload if isinstance(payload, dict) else {}
    url = f"https://api.github.com/search/repositories?{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "dsh-market-catalog"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
        raise FetchError("GitHub 仓库查询失败。") from error
    return payload if isinstance(payload, dict) else {}


def fetch_recent_github_repositories() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """抓取 GitHub 搜索窗口内的最新项目，完整项目快照由本地基线补足。"""
    collected: list[dict[str, Any]] = []
    total_count = 0
    for page in range(1, GITHUB_SEARCH_PAGES + 1):
        payload = github_api_page(page)
        page_items = payload.get("items")
        if not isinstance(page_items, list):
            raise FetchError("GitHub 返回缺少项目列表。")
        total_count = max(total_count, to_int(payload.get("total_count")))
        collected.extend(item for item in page_items if isinstance(item, dict))
        if len(page_items) < 100:
            break
        time.sleep(0.35)
    if not collected:
        raise FetchError("GitHub 本次没有返回任何项目，已停止构建。")
    return collected, {
        "fetchedCount": len(collected),
        "githubReportedCount": total_count,
        "searchWindowLimited": total_count > len(collected),
    }


def format_timestamp(value: str) -> str:
    """把 ISO 时间裁剪成读者容易扫到的本地数据快照文本。"""
    return value.replace("T", " ")[:16] if value else "未提供"


def format_date(value: str | None) -> str:
    """详情页只展示日期，避免把时区不明的时间误写成精确本地时间。"""
    return value[:10] if value else "未提供"


def number_text(value: Any) -> str:
    """以中文目录常见的千位分隔格式输出统计数字。"""
    return f"{to_int(value):,}"


def compact_number_text(value: Any) -> str:
    """把大数字压缩成 Hero 数据卡片适合扫读的格式。"""
    number = to_int(value)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}m".rstrip("0").rstrip(".")
    if number >= 1_000:
        return f"{number / 1_000:.1f}k".rstrip("0").rstrip(".")
    return number_text(number)


def load_template(name: str) -> str:
    """读取生产 HTML、CSS 与 JS 模板。"""
    path = TEMPLATES / name
    if not path.exists():
        raise FileNotFoundError(f"缺少模板文件: {path}")
    return path.read_text(encoding="utf-8")


def render_tokens(template: str, tokens: dict[str, str]) -> str:
    """使用明确的双花括号占位符替换模板变量，避免 CSS 花括号与 format 冲突。"""
    result = template
    for key, value in tokens.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


def build_index(data: dict[str, Any], site_url: str) -> str:
    """渲染首页外壳；实际目录数据由前端从 data.json 读取。"""
    generated = format_timestamp(data["generatedAt"])
    description = "DeepSeek Harness 非官方插件集市。按用途、类型和更新时间浏览 GitHub dsh-plugin Topic 项目。"
    total_stars = sum(to_int(item.get("stars")) for item in data["items"])
    verified_count = sum(1 for item in data["items"] if bool_value(item.get("verified")))
    return render_tokens(
        load_template("index.html"),
        {
            "SITE_URL": html.escape(site_url, quote=True),
            "SITE_URL_JSON": json.dumps(site_url, ensure_ascii=False),
            "PROJECT_COUNT": number_text(data["count"]),
            "CATEGORY_COUNT": str(len(data["categories"])),
            "STAR_COUNT": compact_number_text(total_stars),
            "VERIFIED_COUNT": number_text(verified_count),
            "GENERATED_AT": html.escape(generated),
            "META_DESCRIPTION": html.escape(description, quote=True),
        },
    )


def card_markup(item: dict[str, Any], prefix: str = "../") -> str:
    """详情页中的相似项目继续复用首页卡片的信息顺序。"""
    name = html.escape(item["name"])
    description = html.escape(item["description"] or "这个项目暂未提供说明。")
    owner = html.escape(item["owner"].get("login") or "未知作者")
    language = html.escape(item["language"] or "未标注语言")
    category = html.escape(CATEGORY_LABELS.get(item["category"], "开发与自动化"))
    type_label = html.escape(TYPE_LABELS.get(item["projectType"], "插件"))
    slug = urllib.parse.quote(item["detailSlug"])
    avatar_url = item["owner"].get("avatarUrl") or (
        "https://github.com/" + urllib.parse.quote(item["owner"].get("login") or "github") + ".png?size=80"
    )
    return (
        f'<a class="plugin-card" href="{prefix}{slug}/" aria-label="查看 {name} 的详情">'
        f'<img class="card-avatar" loading="lazy" src="{html.escape(avatar_url, quote=True)}" alt="">'
        '<span class="card-identity">'
        f'<span class="card-context">{category} · {type_label}</span>'
        f'<strong class="card-title">{name}</strong>'
        f'<span class="card-owner">{owner}</span>'
        "</span>"
        '<span class="card-rank" aria-hidden="true"></span>'
        f'<span class="card-description">{description}</span>'
        '<span class="card-meta">'
        f'<span>Star {number_text(item["stars"])}</span><span>{language}</span><span>{format_date(item["pushedAt"])} 更新</span>'
        "</span></a>"
    )


def build_detail(item: dict[str, Any], similar: list[dict[str, Any]], site_url: str) -> str:
    """渲染单个插件详情页，原始仓库链接只在这里出现。"""
    slug = urllib.parse.quote(item["detailSlug"])
    canonical = f"{site_url}/plugins/{slug}/"
    name = html.escape(item["name"])
    description_text = item["description"] or "这个项目暂未提供说明。请以原始仓库内容为准。"
    description = html.escape(description_text)
    github_link = ""
    if item["url"]:
        github_link = (
            f'<a class="action-button action-primary" href="{html.escape(item["url"], quote=True)}" '
            'target="_blank" rel="noopener noreferrer">查看 GitHub 仓库</a>'
        )
    homepage_link = ""
    if item["homepage"]:
        homepage_link = (
            f'<a class="action-button" href="{html.escape(item["homepage"], quote=True)}" '
            'target="_blank" rel="noopener noreferrer">打开项目主页</a>'
        )
    fields = [
        ("Star", number_text(item["stars"])),
        ("派生", number_text(item["forks"])),
        ("语言", item["language"] or "未标注"),
        ("许可证", item["license"] or "未标注"),
        ("创建时间", format_date(item["createdAt"])),
        ("最近更新", format_date(item["pushedAt"])),
    ]
    metadata = "".join(
        f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd></div>" for label, value in fields
    )
    similar_markup = "".join(card_markup(entry) for entry in similar) or '<p class="empty-copy">暂时没有同分类项目可推荐。</p>'
    json_ld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "SoftwareSourceCode",
        "name": item["name"],
        "description": description_text,
        "url": canonical,
        "programmingLanguage": item["language"] or None,
    }
    if item["url"]:
        json_ld["codeRepository"] = item["url"]
    if item["license"]:
        json_ld["license"] = item["license"]
    return render_tokens(
        load_template("detail.html"),
        {
            "SITE_URL": html.escape(site_url, quote=True),
            "CANONICAL_URL": html.escape(canonical, quote=True),
            "CANONICAL_URL_JSON": json.dumps(canonical, ensure_ascii=False),
            "PAGE_NAME": name,
            "PAGE_DESCRIPTION": html.escape(clean_text(description_text, 155), quote=True),
            "DESCRIPTION": description,
            "FULL_NAME": html.escape(item["fullName"]),
            "OWNER": html.escape(item["owner"].get("login") or "未知作者"),
            "CATEGORY": html.escape(CATEGORY_LABELS.get(item["category"], "开发与自动化")),
            "TYPE": html.escape(TYPE_LABELS.get(item["projectType"], "插件")),
            "GITHUB_LINK": github_link,
            "HOMEPAGE_LINK": homepage_link,
            "METADATA_ROWS": metadata,
            "SIMILAR_CARDS": similar_markup,
            "JSON_LD": json.dumps(json_ld, ensure_ascii=False, separators=(",", ":")),
        },
    )


def select_similar(item: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """优先展示同分类且 Star 较高的项目，详情页不凭空编写相关推荐。"""
    candidates = [
        candidate
        for candidate in items
        if candidate["detailSlug"] != item["detailSlug"] and candidate["category"] == item["category"] and not candidate["archived"]
    ]
    candidates.sort(key=lambda candidate: (-candidate["stars"], candidate["name"].lower()))
    return candidates[:3]


def build_sitemap(items: list[dict[str, Any]], site_url: str) -> str:
    """生成静态详情页 sitemap，帮助搜索引擎发现真实可抓取的页面。"""
    urls = [f"{site_url}/"]
    for item in items:
        urls.append(f"{site_url}/plugins/{urllib.parse.quote(item['detailSlug'])}/")
    rows = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        rows.append("  <url>")
        rows.append(f"    <loc>{html.escape(url)}</loc>")
        rows.append("  </url>")
    rows.append("</urlset>")
    return "\n".join(rows) + "\n"


def build_robots(site_url: str) -> str:
    """生成页面实际可访问的 robots.txt，而不是只放 meta robots。"""
    return f"User-agent: *\nAllow: /\n\nSitemap: {site_url}/sitemap.xml\n"


def copy_static_assets() -> None:
    """将前端源文件、品牌图片和搜索验证文件复制到部署目录。"""
    write_text_atomic(SITE / "assets" / "site.css", load_template("site.css"))
    write_text_atomic(SITE / "assets" / "site.js", load_template("site.js"))
    if not WHALE_IMAGE.exists():
        raise FileNotFoundError(f"缺少品牌图片：{WHALE_IMAGE}")
    temporary = SITE / "assets" / f".whale-hero.{os.getpid()}.tmp"
    shutil.copyfile(WHALE_IMAGE, temporary)
    os.replace(temporary, SITE / "assets" / "whale-hero.png")
    if not GOOGLE_VERIFICATION_FILE.exists():
        raise FileNotFoundError(f"缺少 Google 验证文件：{GOOGLE_VERIFICATION_FILE}")
    verification_temporary = SITE / f".{GOOGLE_VERIFICATION_FILE.name}.{os.getpid()}.tmp"
    shutil.copyfile(GOOGLE_VERIFICATION_FILE, verification_temporary)
    os.replace(verification_temporary, SITE / GOOGLE_VERIFICATION_FILE.name)


def build_site(data: dict[str, Any], site_url: str, report: dict[str, Any]) -> None:
    """在所有数据准备完成后再写站点产物。"""
    copy_static_assets()
    write_json_atomic(SITE / "data.json", data)
    write_text_atomic(SITE / "index.html", build_index(data, site_url))
    for item in data["items"]:
        detail_path = SITE / "plugins" / item["detailSlug"] / "index.html"
        write_text_atomic(detail_path, build_detail(item, select_similar(item, data["items"]), site_url))
    write_text_atomic(SITE / "sitemap.xml", build_sitemap(data["items"], site_url))
    write_text_atomic(SITE / "robots.txt", build_robots(site_url))
    write_json_atomic(SITE / "update-report.json", report)


def main() -> int:
    """解析构建参数并返回适合自动化调用的退出码。"""
    parser = argparse.ArgumentParser(description="构建 DSH 插件集市静态站")
    parser.add_argument("--fetch", action="store_true", help="从 GitHub 合并最近更新的 Topic 项目")
    parser.add_argument("--site-url", default=os.environ.get("SITE_URL", DEFAULT_SITE_URL), help="部署站点的公开 URL")
    args = parser.parse_args()
    site_url = safe_url(args.site_url)
    if not site_url:
        print("site-url 必须是 HTTP(S) 地址。", file=sys.stderr)
        return 2
    site_url = site_url.rstrip("/")
    try:
        seed_items, categories, types, curated = load_seed_catalog()
        fetch_meta: dict[str, Any] = {
            "mode": "snapshot",
            "fetchedCount": 0,
            "githubReportedCount": None,
            "searchWindowLimited": False,
        }
        items = seed_items
        if args.fetch:
            fresh_items, metadata = fetch_recent_github_repositories()
            items = merge_catalog_items([seed_items, fresh_items])
            fetch_meta = {"mode": "github-merge", **metadata}
        full_names = {item["fullName"] for item in items}
        curated = [name for name in curated if name in full_names]
        generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        data = {
            "schemaVersion": 2,
            "generatedAt": generated_at,
            "source": "github-topic-dsh-plugin",
            "count": len(items),
            "categories": categories,
            "types": types,
            "curatedOrder": curated,
            "items": items,
        }
        report = {
            "generatedAt": generated_at,
            "siteUrl": site_url,
            "catalogCount": len(items),
            "curatedCount": len(curated),
            "fetch": fetch_meta,
        }
        build_site(data, site_url, report)
    except (FetchError, FileNotFoundError, OSError) as error:
        print(f"构建失败: {error}", file=sys.stderr)
        return 2
    print(f"构建完成: {data['count']} 个项目，{len(curated)} 个推荐，模式 {fetch_meta['mode']}。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
