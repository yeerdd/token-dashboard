# -*- coding: utf-8 -*-
"""
轻量统一计量网关 (Lightweight Metering Gateway)
=================================================
OpenAI 兼容的本地网关：任何 Agent 把 base_url 指向它，它转发请求到真实上游，
并在每次调用后把 usage（model/input/output/cache）写入 SQLite —— 看板读取即精确计费。

用法:
    python gateway.py --port 8090 --upstream https://api.openai.com/v1
    需要环境变量: GATEWAY_API_KEY=<上游 API key>  （或 --api-key 参数）

Agent 配置示例:
    Hermes:   base_url=http://127.0.0.1:8090/v1, api_key=任意
    Codex:    model_provider=openai, base_url=http://127.0.0.1:8090/v1
    OpenCode: --provider openai --base-url http://127.0.0.1:8090/v1

数据: gateway.db 的 usage_logs 表（与 sub2api 同名表，兼容看板采集器）
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gateway.db")

UPSTREAM = ""   # 例: https://api.openai.com/v1
API_KEY = ""    # 上游 API key


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT,
            agent TEXT DEFAULT 'gateway',
            model TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            cache_creation_tokens INTEGER DEFAULT 0,
            reasoning_tokens INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0,
            created_at REAL
        )"""
    )
    con.commit()
    con.close()


def log_usage(model, inp, outp, cache_r, cache_c, reasoning):
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute(
            "INSERT INTO usage_logs (request_id, model, input_tokens, output_tokens, "
            "cache_read_tokens, cache_creation_tokens, reasoning_tokens, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), model or "unknown", inp, outp, cache_r, cache_c,
             reasoning, time.time()),
        )
        con.commit()
        con.close()
    except Exception:
        pass


def extract_usage(resp_body, model):
    """从上游响应提取 usage（OpenAI 格式）。"""
    inp = outp = cache_r = cache_c = reasoning = 0
    try:
        d = json.loads(resp_body)
        u = d.get("usage") or {}
        inp = int(u.get("prompt_tokens") or 0)
        outp = int(u.get("completion_tokens") or 0)
        details = u.get("prompt_tokens_details") or {}
        cache_r = int(details.get("cached_tokens") or 0)
        ct = u.get("completion_tokens_details") or {}
        reasoning = int(ct.get("reasoning_tokens") or 0)
    except Exception:
        pass
    return inp, outp, cache_r, cache_c, reasoning


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 安静模式

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path in ("/health", "/", "/v1/models"):
            body = json.dumps({"status": "ok", "gateway": "metering"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        # 只处理 /v1/chat/completions（其余原样转发也行，但计费只针对聊天）
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        req_model = ""
        try:
            payload = json.loads(body)
            req_model = payload.get("model") or ""
        except Exception:
            payload = None

        # 转发到上游（走系统代理，适配国内网络）
        url = UPSTREAM.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        # 伪装浏览器 UA，绕过 Cloudflare 对 urllib 默认 UA 的拦截（error 1010）
        req.add_header("User-Agent",
                       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        resp_body = b""
        status = 502
        resp_ct = "application/json"
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                resp_body = resp.read()
                status = resp.status
                resp_ct = resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            status = e.code
        except Exception as e:
            resp_body = json.dumps({"error": str(e)}).encode()
            status = 502

        # 记录 usage
        inp, outp, cr, cc, rea = extract_usage(resp_body, req_model)
        if inp + outp > 0:
            log_usage(req_model, inp, outp, cr, cc, rea)

        self.send_response(status)
        self.send_header("Content-Type", resp_ct)
        self._cors()
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)


def main():
    global UPSTREAM, API_KEY
    ap = argparse.ArgumentParser(description="轻量统一计量网关")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--upstream", default=os.environ.get("GATEWAY_UPSTREAM", ""),
                    help="上游 OpenAI 兼容地址，如 https://api.openai.com/v1")
    ap.add_argument("--api-key", default=os.environ.get("GATEWAY_API_KEY", ""),
                    help="上游 API key")
    args = ap.parse_args()

    UPSTREAM = args.upstream
    API_KEY = args.api_key
    if not UPSTREAM:
        print("错误: 需要 --upstream 或环境变量 GATEWAY_UPSTREAM")
        sys.exit(1)
    if not API_KEY:
        print("错误: 需要 --api-key 或环境变量 GATEWAY_API_KEY")
        sys.exit(1)

    init_db()
    print(f"✅ 计量网关已启动: http://127.0.0.1:{args.port}")
    print(f"   上游: {UPSTREAM}")
    print(f"   计费库: {DB_PATH}")
    print(f"   健康检查: http://127.0.0.1:{args.port}/health")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
