#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token 消耗实时看板 —— 跨 Agent 统一用量采集 + 可视化（v2 适配器架构）
====================================================================
数据源自动探测（见 collectors.py）:
  Hermes / OpenCode CLI / Codex / Antigravity(会话级) / Grok(会话级)
  / ZCode / Sub2API网关 / 手动上报

启动:  python server.py [--port 8712] [--all-agents]
"""
import argparse
import json
import mimetypes
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import collectors

# 与 README 和一键启动脚本保持一致：默认只统计当前 Work space。
# 需要全目录统计时显式传入 --all-agents。
collectors.ALL_AGENTS = False

HOST = "127.0.0.1"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE = {"ts": 0.0, "data": None}
CACHE_TTL = 5.0  # 与前端 5s 轮询对齐，避免每次请求都重读数据库


# ---------------------------------------------------------------- 聚合
def aggregate():
    now = time.time()
    if CACHE["data"] is not None and now - CACHE["ts"] < CACHE_TTL:
        return CACHE["data"]
    events, sources = collectors.collect_all()
    data = {"events": events, "sources": sources}
    CACHE["data"] = data
    CACHE["ts"] = now
    return data


def ensure_usage_db():
    con = sqlite3_connect()
    con.execute(
        "CREATE TABLE IF NOT EXISTS reported ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, agent TEXT, model TEXT, "
        "input INTEGER, output INTEGER, cost REAL, note TEXT)"
    )
    con.commit()
    con.close()


def sqlite3_connect():
    import sqlite3
    return sqlite3.connect(os.path.join(BASE_DIR, "usage.db"))


# ---------------------------------------------------------------- API 组装
def api_data():
    agg = aggregate()
    events = agg["events"]
    sources = agg["sources"]
    # 成本补算：数据源没给 cost 的事件，用 pricing 按模型单价估算
    try:
        import pricing
        for e in events:
            if not e.get("cost"):
                e["cost"] = pricing.estimate_cost(
                    e.get("model") or "", e.get("input", 0), e.get("output", 0),
                    e.get("cache_read", 0), e.get("cache_write", 0))
                e["cost_estimated"] = True
    except Exception:
        pass
    now = time.time()
    day = 86400.0
    week = 7 * day

    def sums(evs):
        s = {
            "input": 0, "output": 0, "cache": 0, "cache_read": 0, "cache_write": 0,
            "reasoning": 0, "cost": 0.0, "count": len(evs), "hit_rate": 0.0
        }
        for e in evs:
            s["input"] += e.get("input", 0)
            s["output"] += e.get("output", 0)
            cr = e.get("cache_read", 0)
            cw = e.get("cache_write", 0)
            s["cache_read"] += cr
            s["cache_write"] += cw
            s["cache"] += cr + cw
            s["reasoning"] += e.get("reasoning", 0)
            s["cost"] += e.get("cost", 0.0)
        
        denom = s["input"] + s["cache_read"]
        if denom > 0:
            s["hit_rate"] = round((s["cache_read"] / denom) * 100, 1)
        elif s["input"] + s["cache"] > 0:
            s["hit_rate"] = round((s["cache"] / (s["input"] + s["cache"])) * 100, 1)
        else:
            s["hit_rate"] = 0.0
        return s

    # 「今日」按本地自然日 0 点起算（与 daily_report 一致），不是滚动 24 小时
    lt = time.localtime(now)
    day_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    today = [e for e in events if e["ts"] >= day_start]
    week_evs = [e for e in events if e["ts"] >= now - week]

    models = {}
    for e in events:
        k = e["model"]
        m = models.setdefault(k, {"model": k, "input": 0, "output": 0, "cache": 0, "cost": 0.0, "count": 0, "agents": set()})
        m["input"] += e["input"]; m["output"] += e["output"]
        m["cache"] += e["cache_read"] + e["cache_write"]; m["cost"] += e["cost"]
        m["count"] += 1; m["agents"].add(e["agent"])
    for m in models.values():
        m["agents"] = sorted(m["agents"])
    model_rank = sorted(models.values(), key=lambda m: -(m["input"] + m["output"]))

    agents = {}
    for e in events:
        a = agents.setdefault(e["agent"], {"agent": e["agent"], "input": 0, "output": 0, "cache": 0, "cost": 0.0, "count": 0})
        a["input"] += e["input"]; a["output"] += e["output"]
        a["cache"] += e["cache_read"] + e["cache_write"]; a["cost"] += e["cost"]
        a["count"] += 1
    agent_summary = sorted(agents.values(), key=lambda a: -(a["input"] + a["output"]))

    hourly = []
    for h in range(23, -1, -1):
        start = now - (h + 1) * 3600
        end = now - h * 3600
        bucket = [e for e in events if start <= e["ts"] < end]
        hourly.append({"label": time.strftime("%H:%M", time.localtime(start)),
                       "input": sum(e["input"] for e in bucket),
                       "output": sum(e["output"] for e in bucket)})

    # 近 7 个本地自然日（含今天），total = 新输入+输出+缓存（与前端卡片口径一致）
    daily = []
    for d in range(6, -1, -1):
        start = day_start - d * day
        end = start + day
        bucket = [e for e in events if start <= e["ts"] < end]
        daily.append({
            "label": time.strftime("%m-%d", time.localtime(start)),
            "total": sum(
                e["input"] + e["output"] + e.get("cache_read", 0) + e.get("cache_write", 0)
                for e in bucket
            ),
        })

    for e in events:
        e["time"] = time.strftime("%m-%d %H:%M", time.localtime(e["ts"]))

    recent = sorted(events, key=lambda e: -e["ts"])[:50]

    return {
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "workspace_only": not collectors.ALL_AGENTS,
        "sources": sources,
        "stats": {"today": sums(today), "week": sums(week_evs), "all": sums(events)},
        "model_rank": model_rank,
        "agent_summary": agent_summary,
        "hourly": hourly,
        "daily": daily,
        "recent": recent,
        "events": events,
        "scope": "仅 Work space 工作台" if not collectors.ALL_AGENTS else "全部目录",
    }


# ---------------------------------------------------------------- HTTP 服务
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            f = os.path.join(BASE_DIR, "index.html")
            if os.path.exists(f):
                with open(f, "rb") as fp:
                    self._send(200, fp.read(), "text/html; charset=utf-8")
            else:
                self._send(404, b"index.html not found")
            return
        # 只提供看板目录内的静态资源，避免背景图/字体等相对资源被 404。
        if path not in ("/", "/index.html") and "." in os.path.basename(path):
            rel = urllib.parse.unquote(path.lstrip("/"))
            candidate = os.path.abspath(os.path.join(BASE_DIR, rel))
            if os.path.commonpath((BASE_DIR, candidate)) == BASE_DIR and os.path.isfile(candidate):
                ctype = mimetypes.guess_type(candidate)[0] or "application/octet-stream"
                with open(candidate, "rb") as fp:
                    self._send(200, fp.read(), ctype)
                return
        if path in ("/api/data", "/api/jsonp"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            callback = query.get("callback", [None])[0]
            try:
                data_dict = api_data()
                if callback:
                    body = f"{callback}({json.dumps(data_dict, ensure_ascii=False)});".encode("utf-8")
                    self._send(200, body, "application/javascript; charset=utf-8")
                else:
                    body = json.dumps(data_dict, ensure_ascii=False).encode("utf-8")
                    self._send(200, body)
            except Exception as ex:
                self._send(500, json.dumps({"error": str(ex)}).encode())
            return
        if path == "/api/report-usage":
            self._send(200, json.dumps({
                "method": "POST /api/report",
                "example": {"agent": "Grok", "model": "grok-4.5",
                            "input": 12345, "output": 678, "cost": 0.01,
                            "note": "本次任务说明"},
            }, ensure_ascii=False).encode())
            return
        self._send(404, b"not found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/report":
            try:
                import sqlite3
                ln = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(ln) or b"{}")
                con = sqlite3.connect(os.path.join(BASE_DIR, "usage.db"))
                con.execute(
                    "INSERT INTO reported (ts, agent, model, input, output, cost, note) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (time.time(), data.get("agent", "手动上报"), data.get("model", "?"),
                     int(data.get("input", 0)), int(data.get("output", 0)),
                     float(data.get("cost", 0.0)), data.get("note", "")))
                con.commit(); con.close()
                CACHE["data"] = None
                self._send(200, json.dumps({"ok": True}).encode())
            except Exception as ex:
                self._send(400, json.dumps({"error": str(ex)}).encode())
            return
        self._send(404, b"not found")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8712)
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--workspace-only", action="store_true", help="只统计 Work space 目录（默认）")
    scope.add_argument("--all-agents", action="store_true", help="统计所有本地 Agent 目录")
    args = ap.parse_args()
    collectors.ALL_AGENTS = bool(args.all_agents)
    ensure_usage_db()
    srv = ThreadingHTTPServer((HOST, args.port), Handler)
    print(f"Token 消耗看板已启动: http://{HOST}:{args.port}")
    print(f"统计范围: {'仅 Work space 工作台' if args.workspace_only else '全部 Local Agents (全量)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
