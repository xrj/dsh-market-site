#!/usr/bin/env python3
"""生成 DSH 插件集市的外链候选、评分报告和人工审核草稿。

本脚本只读取本地公开目录快照，不登录第三方平台，也不会自动提交评论、PR、帖子或表单。
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


SITE_BASE = "https://dsh-market.pages.dev"
DEFAULT_DATA = Path("site/data.json")
DEFAULT_OUT = Path("research/backlinks")
TOPIC_WORDS = {
    "dsh",
    "dsh-plugin",
    "dsh-plugins",
    "deepseek",
    "deepseek-harness",
    "agent",
    "agent-skill",
    "mcp",
    "model-context-protocol",
}


def read_json(path: Path) -> dict[str, Any]:
    """读取 UTF-8 JSON 文件，并在格式错误时给出明确提示。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"找不到目录数据文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"目录数据不是有效 JSON：{path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    """以稳定格式写出报告，避免每日更新产生无意义的排序变化。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def parse_date(value: str | None) -> datetime | None:
    """解析 GitHub 常见的 ISO 时间，解析失败时返回空值。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def clean_text(value: Any, limit: int = 180) -> str:
    """把外部项目描述压成安全的单行 Markdown 文本。"""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.replace("|", "\\|")
    return text[:limit] + ("…" if len(text) > limit else "")


def detail_url(item: dict[str, Any]) -> str:
    """生成站内详情页地址，优先使用构建器已经确定的 detailSlug。"""
    slug = item.get("detailSlug") or item.get("slug") or item.get("name")
    return f"{SITE_BASE}/plugins/{quote(str(slug).strip('/'))}/"


def score_item(item: dict[str, Any], now: datetime) -> dict[str, Any]:
    """按照主题相关性、项目质量、更新活跃度和风险计算候选分数。"""
    topics = {str(topic).lower() for topic in item.get("topics", [])}
    description = str(item.get("description") or "").lower()
    topic_hits = len(topics & TOPIC_WORDS)
    if "deepseek harness" in description:
        topic_hits += 1
    relevance = min(35, 20 + topic_hits * 5)

    stars = max(0, int(item.get("stars") or 0))
    forks = max(0, int(item.get("forks") or 0))
    authority = min(25, round(math.log10(stars + 1) * 10 + math.log10(forks + 1) * 3, 1))

    pushed_at = parse_date(item.get("pushedAt") or item.get("updatedAt"))
    age_days = 9999
    if pushed_at:
        age_days = max(0, (now - pushed_at).days)
    freshness = 15 if age_days <= 30 else 10 if age_days <= 90 else 5 if age_days <= 365 else 0

    project_type = str(item.get("projectType") or "").lower()
    fit = 15 if project_type in {"plugin", "skill", "collection"} else 8
    risk_penalty = 20 if item.get("archived") or item.get("fork") else 0
    total = max(0, min(100, round(relevance + authority + freshness + fit - risk_penalty)))
    priority = "高" if total >= 65 else "中" if total >= 50 else "低"

    return {
        "relevance": relevance,
        "authority": authority,
        "freshness": freshness,
        "fit": fit,
        "riskPenalty": risk_penalty,
        "total": total,
        "priority": priority,
        "ageDays": age_days,
    }


def make_repo_candidate(item: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    """把一个项目转换成需要人工确认的 README 外链候选。"""
    full_name = str(item.get("fullName") or "").strip()
    name = clean_text(item.get("name") or full_name.split("/")[-1], 100)
    return {
        "id": f"github-readme:{full_name.lower()}",
        "candidateType": "github-readme",
        "source": "github-topic-snapshot",
        "evidenceStatus": "local-snapshot",
        "status": "candidate",
        "autoPublish": False,
        "score": score,
        "project": {
            "name": name,
            "fullName": full_name,
            "url": item.get("url"),
            "homepage": item.get("homepage"),
            "stars": item.get("stars", 0),
            "forks": item.get("forks", 0),
            "topics": item.get("topics", []),
            "description": clean_text(item.get("description")),
        },
        "targetUrl": detail_url(item),
        "suggestedAnchor": f"DSH 插件集市中的{name}",
        "suggestedAction": "联系仓库作者，建议在 README 的安装、相关资源或生态章节添加站内详情页；必须由作者同意后再提交修改。",
        "reviewChecks": [
            "确认该项目仍由作者维护且没有归档或明显重复内容",
            "确认链接放在 README 的自然上下文中，而不是隐藏或堆砌关键词",
            "确认作者同意后再创建 PR，不使用机器人批量开 PR",
        ],
    }


def make_owner_candidate(item: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    """为高质量项目作者生成一条低频、个性化联系候选。"""
    owner = str((item.get("owner") or {}).get("login") or "").strip()
    name = clean_text(item.get("name") or item.get("fullName"), 100)
    return {
        "id": f"github-owner:{owner.lower()}",
        "candidateType": "github-owner-outreach",
        "source": "github-topic-snapshot",
        "evidenceStatus": "local-snapshot",
        "status": "candidate",
        "autoPublish": False,
        "score": {**score, "total": max(0, score["total"] - 5)},
        "project": {
            "name": name,
            "fullName": item.get("fullName"),
            "url": item.get("url"),
            "owner": owner,
        },
        "targetUrl": detail_url(item),
        "suggestedAction": "准备一封针对该项目的短联系稿，请作者自行决定是否在项目文档中引用集市详情页。",
        "reviewChecks": [
            "只联系与项目高度相关的作者，不群发相同内容",
            "不索要付费链接，不承诺排名或流量",
            "记录联系日期和对方是否明确同意",
        ],
    }


def channel_seeds() -> list[dict[str, Any]]:
    """提供需要人工核验投稿规则的渠道种子，不把它们伪装成已确认外链。"""
    seeds = [
        ("GitHub Awesome List", "https://github.com/search?q=awesome+deepseek&type=repositories", "寻找明确允许贡献的 AI、MCP 或 DeepSeek Awesome List"),
        ("GitHub Topic", "https://github.com/topics/dsh-plugin", "观察主题页和高质量项目，不能把主题页本身当作可控外链"),
        ("掘金", "https://juejin.cn/", "只发布有实测内容的教程，先核对社区外链规则"),
        ("V2EX", "https://www.v2ex.com/", "只在相关讨论中提供有帮助的内容，禁止重复发帖"),
        ("知乎", "https://www.zhihu.com/", "优先回答真实问题，链接只作为补充资料"),
        ("Reddit", "https://www.reddit.com/", "先确认版规和社区相关性，再决定是否投稿"),
    ]
    return [
        {
            "id": f"channel-seed:{name.lower().replace(' ', '-')}",
            "candidateType": "channel-research",
            "source": "curated-seed",
            "evidenceStatus": "unverified",
            "status": "research-required",
            "autoPublish": False,
            "score": {"total": 45, "priority": "中"},
            "targetName": name,
            "targetUrl": url,
            "suggestedAction": action,
            "reviewChecks": ["核对当前投稿规则", "确认内容与社区主题匹配", "人工发布并记录最终 URL"],
        }
        for name, url, action in seeds
    ]


def build_report(data: dict[str, Any], out_dir: Path, limit: int) -> dict[str, Any]:
    """生成候选 JSON、Markdown 报告和人工审核草稿。"""
    now = datetime.now(timezone.utc)
    items = data.get("items") or []
    scored = []
    for item in items:
        if not item.get("url") or not item.get("fullName"):
            continue
        score = score_item(item, now)
        if score["riskPenalty"]:
            continue
        scored.append((score["total"], item, score))
    scored.sort(key=lambda row: (row[0], int(row[1].get("stars") or 0), row[1].get("fullName", "")), reverse=True)

    repo_candidates = [make_repo_candidate(item, score) for _, item, score in scored[:limit]]
    owner_candidates = []
    seen_owners: set[str] = set()
    for _, item, score in scored:
        owner = str((item.get("owner") or {}).get("login") or "").lower()
        if not owner or owner in seen_owners:
            continue
        seen_owners.add(owner)
        owner_candidates.append(make_owner_candidate(item, score))
        if len(owner_candidates) >= min(50, limit):
            break

    candidates = repo_candidates + owner_candidates + channel_seeds()
    generated_at = now.isoformat(timespec="seconds")
    result = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "source": {"path": str(DEFAULT_DATA), "catalogGeneratedAt": data.get("generatedAt"), "catalogCount": len(items)},
        "policy": {
            "autoPublish": False,
            "humanApprovalRequired": True,
            "disallowed": ["批量评论", "论坛灌水", "PBN", "隐藏链接", "购买链接", "重复锚文本群发"],
        },
        "counts": {
            "repoReadme": len(repo_candidates),
            "ownerOutreach": len(owner_candidates),
            "channelResearch": len(channel_seeds()),
            "total": len(candidates),
        },
        "candidates": candidates,
    }
    write_json(out_dir / "backlink-prospects.json", result)

    top = candidates[:30]
    markdown = [
        "# DSH 外链候选池",
        "",
        f"生成时间：`{generated_at}`（UTC）",
        f"目录快照：`{len(items)}` 个项目，快照时间：`{data.get('generatedAt') or '未知'}`",
        "",
        "> 本报告只生成候选和草稿，不会自动创建 PR、发帖、评论或联系用户。所有第三方指标都需要单独核验。",
        "",
        "## 候选统计",
        "",
        f"- README 候选：{len(repo_candidates)}",
        f"- 作者联系候选：{len(owner_candidates)}",
        f"- 渠道研究种子：{len(channel_seeds())}",
        "",
        "## 优先处理的候选",
        "",
        "| 优先级 | 分数 | 类型 | 项目/渠道 | 建议目标 | 状态 |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for candidate in top:
        score = candidate.get("score", {})
        project = candidate.get("project") or {}
        label = project.get("fullName") or candidate.get("targetName") or "未命名"
        markdown.append(
            f"| {score.get('priority', '未知')} | {score.get('total', 0)} | {candidate.get('candidateType')} | {clean_text(label, 70)} | {candidate.get('targetUrl', '')} | {candidate.get('status')} |"
        )
    markdown.extend(
        [
            "",
            "## 审核原则",
            "",
            "1. 先确认页面主题和投稿规则，再决定是否联系或提交。",
            "2. 链接必须放在自然上下文中，优先使用具体插件详情页，不把所有链接都指向首页。",
            "3. 未经人工确认，不调用任何第三方写入接口。",
            "",
        ]
    )
    (out_dir / "backlink-prospects.md").write_text("\n".join(markdown), encoding="utf-8")

    drafts = [
        "# 外链沟通草稿（人工审核）",
        "",
        "> 以下内容仅供逐条修改后使用，不要批量复制粘贴。发布前必须得到项目作者或平台规则允许。",
        "",
    ]
    for candidate in repo_candidates[:30]:
        project = candidate["project"]
        drafts.extend(
            [
                f"## {project['fullName']}",
                "",
                f"项目：{project['url']}",
                f"建议目标：{candidate['targetUrl']}",
                "",
                "### README 建议文案",
                "",
                f"如果你想让用户更快找到同类工具，可以在 README 的相关资源处补充：[DSH 插件集市中的 {project['name']}]({candidate['targetUrl']})。",
                "",
                "### English alternative",
                "",
                f"You can also list this project in the [DSH Plugin Marketplace]({candidate['targetUrl']}) so users can discover it by use case.",
                "",
                "### 审核状态",
                "",
                "- [ ] 已核对 README 结构和贡献规范",
                "- [ ] 已人工改写为符合项目语气的文案",
                "- [ ] 已获得作者同意",
                "- [ ] 已记录最终链接和发布日期",
                "",
            ]
        )
    (out_dir / "drafts" / "github-readme-outreach.md").write_text("\n".join(drafts), encoding="utf-8")
    return result


def main() -> int:
    """解析命令行参数并生成外链候选文件。"""
    parser = argparse.ArgumentParser(description="生成 DSH 外链候选和人工审核草稿")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="目录数据 JSON 路径")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT, help="报告输出目录")
    parser.add_argument("--limit", type=int, default=200, help="README 候选上限")
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit("--limit 必须大于 0")
    data = read_json(args.data)
    result = build_report(data, args.out_dir, args.limit)
    print(
        f"外链候选生成完成：{result['counts']['total']} 条候选，"
        f"其中 README {result['counts']['repoReadme']} 条、作者 {result['counts']['ownerOutreach']} 条。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
