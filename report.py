#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用 Token 消耗上报工具 —— 补齐自动采集缺失或覆盖估算值。

用法示例：
  python report.py --agent Antigravity --model gemini-3.6-flash --input 9999 --output 1234 --note "精确账单"
  python report.py --agent 其他工具 --model foo --input 100 --output 20

参数说明：
  --agent   来源 Agent 名（必填）
  --model   使用的模型名（必填）
  --input   输入 token 数
  --output  输出 token 数
  --cost    已忽略（看板不再统计价格，可省略）
  --note    任务说明（可选）
  --url     看板服务地址（默认 http://127.0.0.1:8712）

注意：
  - 看板只认 token 数；Hermes/OpenCode/Codex/Grok 已自动采集真实 usage。
  - Antigravity 仅在本地 task log 有 API usage 时自动计入，否则请手动上报。
  - 与自动源同名时显示为「手动·Agent」，避免双计。
"""
import argparse
import json
import sys
import urllib.request


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="上报 Token 消耗到看板")
    ap.add_argument("--agent", required=True, help="Agent 名称")
    ap.add_argument("--model", required=True, help="模型名称")
    ap.add_argument("--input", type=int, default=0, help="输入 tokens")
    ap.add_argument("--output", type=int, default=0, help="输出 tokens")
    ap.add_argument("--cost", type=float, default=0.0, help="成本 USD")
    ap.add_argument("--note", default="", help="说明")
    ap.add_argument("--url", default="http://127.0.0.1:8712", help="看板地址")
    args = ap.parse_args()

    payload = {
        "agent": args.agent, "model": args.model,
        "input": args.input, "output": args.output,
        "cost": args.cost, "note": args.note,
    }
    req = urllib.request.Request(
        args.url + "/api/report",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
        if body.get("ok"):
            print(f"OK 已上报: {args.agent} / {args.model} / in={args.input} out={args.output}")
        else:
            print("✗ 上报失败:", body)
            sys.exit(1)
    except Exception as ex:
        print(f"✗ 无法连接看板 ({args.url}): {ex}")
        print("  请确认看板服务已启动: python server.py")
        sys.exit(1)


if __name__ == "__main__":
    main()
