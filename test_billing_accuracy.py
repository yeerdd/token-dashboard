# -*- coding: utf-8 -*-
"""Regression: real tokens only + source reconcile + 计费口径契约."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collectors


def main():
    collectors.ALL_AGENTS = False
    events, sources = collectors.collect_all()
    assert isinstance(events, list)

    for e in events:
        assert e.get("estimated") is False, e
        assert float(e.get("cost") or 0) == 0.0, e
        assert e["input"] + e["output"] > 0, e
        # 计费契约：所有字段非负；缓存与输入分离（input 不含 cache）
        assert e["input"] >= 0 and e["output"] >= 0, e
        assert e["cache_read"] >= 0 and e["cache_write"] >= 0, e
        assert e["reasoning"] >= 0, e

    # 防估算回归：collectors 源码不得再出现字符估算 / 估算成本
    src = open(os.path.join(os.path.dirname(__file__), "collectors.py"), encoding="utf-8").read()
    assert "import pricing" not in src
    assert "estimate_cost" not in src
    assert "_estimate_transcript_tokens" not in src
    assert "estimated=True" not in src

    # 口径契约：前端消耗卡片必须等于 input+output（不得把缓存计入总消耗）
    html = open(os.path.join(os.path.dirname(__file__), "index.html"), encoding="utf-8").read()
    for line in (
        "setNum('all', s.all.input + s.all.output)",
        "setNum('today', s.today.input + s.today.output)",
        "setNum('week', s.week.input + s.week.output)",
        "setNum('all', aSum.input + aSum.output)",
        "setNum('today', tSum.input + tSum.output)",
        "setNum('week', wSum.input + wSum.output)",
    ):
        assert line in html, f"口径契约缺失: {line}"
    # 筛选视图「今日」必须用本地自然日（dayStart），不得退回滚动 24h
    assert "dayStart" in html, "筛选视图今日必须是自然日口径 (dayStart)"
    assert "now - daySec);" not in html, "滚动 24h 口径回归: todayEvs 不能用 now - daySec"

    # AG extractor must find known session if present
    sdir = os.path.join(
        os.path.expanduser("~"),
        ".gemini", "antigravity", "brain",
        "05803c03-e155-484f-b79d-78b6ed21a13d",
    )
    if os.path.isdir(sdir):
        u = collectors._extract_task_usage(sdir)
        assert u is not None, "known AG task-log usage missing"
        assert u[0] + u[1] > 0

    # AG real usage should appear in collect (cwd-less Pro session allowed)
    ag = [e for e in events if e["agent"] == "Antigravity"]
    if os.path.isdir(sdir) and collectors._extract_task_usage(sdir):
        assert len(ag) >= 1, "AG real usage not collected"

    print("SOURCES", sources)
    by = {}
    for e in events:
        by[e["agent"]] = by.get(e["agent"], 0) + 1
    print("BY_AGENT", by)
    print("events", len(events),
          "in", sum(e["input"] for e in events),
          "out", sum(e["output"] for e in events))
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
