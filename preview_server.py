# -*- coding: utf-8 -*-
"""快速预览服务器 — 提供静态文件 + 模拟 API 数据"""
import json, os, time, random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8765

AGENTS = ["Antigravity", "Hermes", "Codex", "Grok", "ZCode", "OpenCode", "DSH"]
MODELS = ["claude-sonnet-4", "gpt-4o", "gemini-2.5-flash", "deepseek-v3", "o3-mini", "claude-haiku-4", "grok-3"]
NOTES = ["代码重构", "API 调试", "文档生成", "数据分析", "Bug 修复", "测试编写", "架构设计", "性能优化", "安全审查", "部署脚本"]

def gen_events():
    events = []
    now = time.time()
    for i in range(180):
        ts = now - random.randint(0, 7 * 86400)
        agent = random.choice(AGENTS)
        model = random.choice(MODELS)
        inp = random.randint(500, 50000)
        outp = random.randint(200, 20000)
        cr = random.randint(0, inp // 3)
        cw = random.randint(0, inp // 5)
        rea = random.randint(0, outp // 4) if random.random() > 0.5 else 0
        events.append({
            "ts": ts, "agent": agent, "model": model,
            "input": inp, "output": outp,
            "cache_read": cr, "cache_write": cw,
            "reasoning": rea, "cost": 0.0,
            "note": random.choice(NOTES),
            "time": time.strftime("%m/%d %H:%M", time.localtime(ts))
        })
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events

def gen_mock_data():
    events = gen_events()
    now = time.time()
    day_start = int(time.mktime(time.strftime("%Y-%m-%d", time.localtime(now)).encode() and time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d")))

    today_evs = [e for e in events if e["ts"] >= day_start]
    week_evs = [e for e in events if e["ts"] >= now - 7 * 86400]

    def stats(arr):
        inp = sum(e["input"] for e in arr)
        outp = sum(e["output"] for e in arr)
        cr = sum(e["cache_read"] for e in arr)
        cw = sum(e["cache_write"] for e in arr)
        cache = cr + cw
        rea = sum(e["reasoning"] for e in arr)
        hr = round(cr / (inp + cr) * 100, 1) if (inp + cr) > 0 else 0
        return {"input": inp, "output": outp, "cache": cache, "cache_read": cr,
                "cache_write": cw, "hit_rate": hr, "reasoning": rea, "count": len(arr), "cost": 0}

    daily = []
    for d in range(6, -1, -1):
        ds = now - d * 86400
        de = ds - 86400
        day_evs = [e for e in events if de <= e["ts"] < ds]
        total = sum(e["input"] + e["output"] for e in day_evs)
        daily.append({"label": time.strftime("%m/%d", time.localtime(ds)), "total": total})

    sources = []
    for a in AGENTS:
        cnt = len([e for e in events if e["agent"] == a])
        sources.append({"name": a, "active": cnt > 0, "count": cnt})

    return {
        "scope": "Work space 工作台",
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "events": events,
        "recent": events,
        "sources": sources,
        "stats": {
            "today": stats(today_evs),
            "week": stats(week_evs),
            "all": stats(events)
        },
        "daily": daily
    }

class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/data":
            data = gen_mock_data()
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/":
            path = "/index.html"

        filepath = os.path.join(BASE_DIR, path.lstrip("/"))
        if os.path.isfile(filepath):
            with open(filepath, "rb") as f:
                body = f.read()
            ct = "application/octet-stream"
            if path.endswith(".html"): ct = "text/html; charset=utf-8"
            elif path.endswith(".css"): ct = "text/css"
            elif path.endswith(".js"): ct = "application/javascript"
            elif path.endswith(".png"): ct = "image/png"
            elif path.endswith(".jpg"): ct = "image/jpeg"
            elif path.endswith(".mp4"): ct = "video/mp4"
            elif path.endswith(".woff2"): ct = "font/woff2"
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/report":
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    print(f"Preview server running at http://localhost:{PORT}")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
