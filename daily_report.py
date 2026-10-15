#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日 Token 消耗报告 —— 只统计真实 token 数（不含价格）
=====================================================
手动运行：python daily_report.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collectors


def fmt(n):
    if n is None:
        return "0"
    if n >= 1e9:
        return f"{n/1e9:.2f}B"
    if n >= 1e6:
        return f"{n/1e6:.2f}M"
    if n >= 1e3:
        return f"{n/1e3:.1f}K"
    return str(int(n))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    collectors.ALL_AGENTS = False
    events, sources = collectors.collect_all()

    now = time.time()
    day = 86400.0
    week = 7 * day

    lt = time.localtime()
    day_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    today = [e for e in events if e["ts"] >= day_start]
    yesterday = [e for e in events if day_start - day <= e["ts"] < day_start]
    week_evs = [e for e in events if e["ts"] >= now - week]

    def sums(evs):
        s = {"in": 0, "out": 0, "cache": 0, "n": len(evs)}
        for e in evs:
            s["in"] += e["input"]
            s["out"] += e["output"]
            s["cache"] += e["cache_read"] + e["cache_write"]
        return s

    t, y, w = sums(today), sums(yesterday), sums(week_evs)

    by_agent = {}
    for e in today:
        a = by_agent.setdefault(e["agent"], {"in": 0, "out": 0, "cache": 0, "n": 0})
        a["in"] += e["input"]
        a["out"] += e["output"]
        a["cache"] += e["cache_read"] + e["cache_write"]
        a["n"] += 1
    agent_rows = sorted(by_agent.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"]))

    by_model = {}
    for e in today:
        m = by_model.setdefault(e["model"], {"in": 0, "out": 0, "n": 0})
        m["in"] += e["input"]
        m["out"] += e["output"]
        m["n"] += 1
    model_rows = sorted(by_model.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"]))[:8]

    active = [s["name"] for s in sources if s["active"]]
    inactive = [s["name"] for s in sources if not s["active"]]

    date_str = time.strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"Token 消耗日报 · {date_str}")
    lines.append("")
    lines.append(f"**今日** 输入 {fmt(t['in'])} · 输出 {fmt(t['out'])} · 缓存 {fmt(t['cache'])}")
    lines.append(f"**昨日** 输入 {fmt(y['in'])} · 输出 {fmt(y['out'])} · 缓存 {fmt(y['cache'])}")
    lines.append(f"**近 7 天** 共 {fmt(w['in'] + w['out'] + w['cache'])} tokens（in+out+cache）")
    lines.append("")

    if agent_rows:
        lines.append("**今日各 Agent 消耗**")
        for name, a in agent_rows:
            lines.append(
                f"- {name}: {fmt(a['in'] + a['out'] + a['cache'])} "
                f"（in {fmt(a['in'])} / out {fmt(a['out'])} / cache {fmt(a['cache'])}）· {a['n']} 条"
            )
        lines.append("")

    if model_rows:
        lines.append("**今日模型排行**")
        for name, m in model_rows:
            lines.append(f"- {name}: {fmt(m['in'] + m['out'])} tokens（{m['n']} 条）")
        lines.append("")

    lines.append(f"**数据源** 已接入 {len(active)} 个：{', '.join(active)}")
    if inactive:
        lines.append(f"未检测到：{', '.join(inactive)}")
    lines.append("")
    lines.append(
        "> 仅统计 Work space。只收录源端真实 token（Hermes/OpenCode/Codex/Grok 自动；"
        "Antigravity 仅 task-log 真实 usage；无真实记录则不计）。本报告不含价格。"
    )

    print("\n".join(lines))


if __name__ == "__main__":
    main()
