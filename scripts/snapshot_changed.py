#!/usr/bin/env python3
"""判断构建后的目录快照是否有实质变化，忽略每次构建更新的时间戳。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    """读取并校验快照对象。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"快照不是 JSON 对象：{path}")
    return value


def comparable(value: dict[str, Any]) -> dict[str, Any]:
    """删除只代表构建时间的字段，避免没有数据变化时每天产生空提交。"""
    copied = dict(value)
    copied.pop("generatedAt", None)
    return copied


def main() -> int:
    """比较两个快照，变化时返回 0，无变化时返回 1。"""
    parser = argparse.ArgumentParser(description="检查目录快照是否有实质变化")
    parser.add_argument("--before", type=Path, required=True, help="构建前快照")
    parser.add_argument("--current", type=Path, required=True, help="构建后快照")
    args = parser.parse_args()
    changed = comparable(load(args.before)) != comparable(load(args.current))
    print("目录快照有实质变化。" if changed else "目录快照只有时间戳变化。")
    return 0 if changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
