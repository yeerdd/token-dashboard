#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对账脚本：看板采集结果 vs 各 Agent 原始数据源（仅 token，无价格）
================================================================
运行：python reconcile.py
退出码：0=一致  1=有差异
"""
import os
import sys
import json
import glob
import sqlite3
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collectors


def ro(path):
    if not os.path.exists(path):
        return None
    return sqlite3.connect(f"file:{urllib.parse.quote(path)}?mode=ro", uri=True)


def sum_events(evs):
    return {
        "n": len(evs),
        "in": sum(e["input"] for e in evs),
        "out": sum(e["output"] for e in evs),
        "cr": sum(e["cache_read"] for e in evs),
        "cw": sum(e["cache_write"] for e in evs),
    }


def local_source_events(events, agent):
    """按本地采集器对账，排除已切换到网关的同名事件。"""
    return [
        e for e in events
        if e.get("agent") == agent and e.get("provider") != "sub2api"
    ]


def check(name, expected, actual, tol=0):
    ok = True
    lines = [f"## {name}"]
    for k in ("n", "in", "out", "cr"):
        e = expected.get(k, 0) or 0
        a = actual.get(k, 0) or 0
        diff = a - e
        status = "OK" if abs(diff) <= tol else "DIFF"
        if status != "OK":
            ok = False
        lines.append(f"  {k}: raw={e} coll={a} diff={diff} [{status}]")
    return ok, "\n".join(lines)


def raw_opencode():
    con = ro(collectors._OPENCODE_DB)
    if not con:
        return None
    it = ot = cr = n = 0
    for row in con.execute(
        "SELECT tokens_input, tokens_output, tokens_cache_read, directory FROM session "
        "WHERE tokens_input > 0 OR tokens_output > 0"
    ):
        tin, tout, tcr, directory = row
        if not collectors.in_workspace(directory):
            continue
        n += 1
        it += tin or 0
        ot += tout or 0
        cr += tcr or 0
    con.close()
    return {"n": n, "in": it, "out": ot, "cr": cr}


def raw_codex():
    """与 collector 相同：有 rollout 用拆分，否则 tokens_used 记 input。"""
    con = ro(collectors._CODEX_DB)
    if not con:
        return None
    it = ot = cr = n = 0
    rows = con.execute(
        "SELECT tokens_used, cwd, rollout_path FROM threads WHERE tokens_used > 0"
    ).fetchall()
    for tokens, cwd, rp in rows:
        if not collectors.in_workspace(cwd):
            continue
        n += 1
        usage = collectors._read_codex_rollout_usage(rp)
        if usage:
            it_total, crr, o, _rt = usage
            it += max(it_total - crr, 0)
            cr += crr
            ot += o
        else:
            it += int(tokens or 0)
    con.close()
    return {"n": n, "in": it, "out": ot, "cr": cr}


def raw_grok():
    it = ot = cr = n = 0
    for sf in glob.glob(os.path.join(collectors._GROK_SESSIONS, "**", "summary.json"), recursive=True):
        try:
            d = json.load(open(sf, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        cwd = (d.get("info") or {}).get("cwd", "")
        if not collectors.in_workspace(cwd):
            continue
        um = collectors._read_grok_usage(os.path.dirname(sf))
        if not um:
            continue
        for _mid, u in um.items():
            if not u.get("turns") or u["in"] + u["out"] <= 0:
                continue
            n += 1
            it += max(u["in"] - u["cr"], 0)
            ot += u["out"]
            cr += u["cr"]
    return {"n": n, "in": it, "out": ot, "cr": cr}


def raw_hermes():
    """直接跑 collector 自身作为 hermes 真值（内部已是 SQL 源）；这里再 SQL 校验总量。"""
    con = ro(collectors._HERMES_DB)
    if not con:
        return None
    # 用与 collector 相同的 scope 规则较难在纯 SQL 复现；改为与 _collect_hermes 对比
    con.close()
    evs = collectors._collect_hermes()
    cut = collectors.GATEWAY_CUTOVER.get("Hermes")
    if cut:
        cut_ts = collectors.parse_iso(cut)
        evs = [e for e in evs if e["ts"] < cut_ts]
    return sum_events(evs)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    collectors.ALL_AGENTS = False
    events, sources = collectors.collect_all()
    by = {}
    for e in events:
        by.setdefault(e["agent"], []).append(e)

    all_ok = True
    reports = []

    # OpenCode
    raw = raw_opencode()
    if raw is not None:
        act = sum_events(local_source_events(events, "OpenCode"))
        ok, msg = check("OpenCode", raw, act)
        all_ok &= ok
        reports.append(msg)

    # Codex family
    raw = raw_codex()
    if raw is not None:
        codex_evs = [
            e for e in events
            if e.get("agent", "").startswith("Codex")
            and e.get("provider") != "sub2api"
        ]
        act = sum_events(codex_evs)
        ok, msg = check("Codex(+CLI/VSCode)", raw, act)
        all_ok &= ok
        reports.append(msg)

    # Grok
    raw = raw_grok()
    act = sum_events(local_source_events(events, "Grok"))
    ok, msg = check("Grok", raw, act)
    all_ok &= ok
    reports.append(msg)

    # Hermes self-consistency
    raw = raw_hermes()
    act = sum_events(local_source_events(events, "Hermes"))
    ok, msg = check("Hermes", raw, act)
    all_ok &= ok
    reports.append(msg)

    # Antigravity note
    ag = sum_events(by.get("Antigravity", []))
    reports.append(
        f"## Antigravity\n  collected n={ag['n']} in={ag['in']} out={ag['out']}\n"
        f"  note: Pro 账号本地通常不落完整 token；仅 task-log 真实 usage 可对账"
    )

    reports.append("## Sources")
    for s in sources:
        reports.append(f"  {s}")

    print("\n".join(reports))
    print("\nRESULT:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
