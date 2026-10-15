# -*- coding: utf-8 -*-
"""
模型单价表 + 成本估算
========================
数据源自带 cost 时优先用数据源（OpenCode 的 cost、Hermes 的 estimated_cost_usd）；
数据源没有成本（Codex / Grok / Antigravity / Hermes 部分模型）时，用本表按
「每百万 token 单价」估算，前端以 ≈ 前缀标识估算成本。

单价来源：
- deepseek-v4-flash：由 OpenCode 真实账单反推（两会话联立求解 Pi/Po/Pc）
- gpt-5.6-luna：由 OpenCode 账单反推（假设 Po=4Pi、Pcr=0.05Pi、Pcw=Pi）
- gemini-3.6-flash / gemini-3.5-flash-lite：由 Hermes estimated_cost_usd 反推
- gpt-5.6-terra/sol、gpt-5.5：按 OpenAI 系 5.x 常见公开价
- grok-4.5：按 xAI 公开价
- kimi-k3 / qwen3.8-max：按厂商公开价
- 未知模型：回退默认价

价格单位：USD / 1M tokens。改这里即可调整估算，无需改采集逻辑。
"""
import re

PRICES = {
    # 模型 id 前缀 -> {input, output, cache_read, cache_write}
    "deepseek-v4-flash":   {"input": 0.070,  "output": 0.280, "cache_read": 0.0015, "cache_write": 0.070},
    "deepseek-chat":       {"input": 0.270,  "output": 1.100, "cache_read": 0.070,  "cache_write": 0.270},
    "deepseek-reasoner":   {"input": 0.550,  "output": 2.190, "cache_read": 0.140,  "cache_write": 0.550},
    "kimi-k3":             {"input": 0.600,  "output": 2.500, "cache_read": 0.100,  "cache_write": 0.600},
    "kimi-k2":             {"input": 0.600,  "output": 2.500, "cache_read": 0.100,  "cache_write": 0.600},
    "gemini-3.6-flash":    {"input": 1.690,  "output": 6.760, "cache_read": 0.0845, "cache_write": 1.690},
    "gemini-3.6-pro":      {"input": 2.500,  "output": 15.00, "cache_read": 0.125,  "cache_write": 2.500},
    "gemini-3.5-flash":    {"input": 0.350,  "output": 1.400, "cache_read": 0.0175, "cache_write": 0.350},
    "gemini-3.5-flash-lite": {"input": 0.350, "output": 1.400, "cache_read": 0.0175, "cache_write": 0.350},
    "gemini":              {"input": 0.350,  "output": 1.400, "cache_read": 0.0175, "cache_write": 0.350},
    "gpt-5.6-luna":        {"input": 0.080,  "output": 0.320, "cache_read": 0.004,  "cache_write": 0.080},
    "gpt-5.6-terra":       {"input": 1.250,  "output": 10.00, "cache_read": 0.125,  "cache_write": 1.250},
    "gpt-5.6-sol":         {"input": 1.250,  "output": 10.00, "cache_read": 0.125,  "cache_write": 1.250},
    "gpt-5.5":             {"input": 1.250,  "output": 10.00, "cache_read": 0.125,  "cache_write": 1.250},
    "gpt-5":               {"input": 1.250,  "output": 10.00, "cache_read": 0.125,  "cache_write": 1.250},
    "gpt-4":               {"input": 1.250,  "output": 10.00, "cache_read": 0.125,  "cache_write": 1.250},
    "grok-4.5":            {"input": 2.000,  "output": 10.00, "cache_read": 0.200,  "cache_write": 2.000},
    "grok-4":              {"input": 2.000,  "output": 10.00, "cache_read": 0.200,  "cache_write": 2.000},
    "grok-3":              {"input": 3.000,  "output": 15.00, "cache_read": 0.300,  "cache_write": 3.000},
    "grok":                {"input": 2.000,  "output": 10.00, "cache_read": 0.200,  "cache_write": 2.000},
    "claude-opus":         {"input": 15.00,  "output": 75.00, "cache_read": 1.500,  "cache_write": 18.75},
    "claude-sonnet":       {"input": 3.000,  "output": 15.00, "cache_read": 0.300,  "cache_write": 3.750},
    "claude-haiku":        {"input": 1.000,  "output": 5.000, "cache_read": 0.100,  "cache_write": 1.250},
    "qwen3":               {"input": 0.400,  "output": 1.600, "cache_read": 0.100,  "cache_write": 0.400},
}

# 未知模型回退价
DEFAULT_PRICE = {"input": 0.500, "output": 1.500, "cache_read": 0.050, "cache_write": 0.500}


def normalize_model(model):
    """去掉 provider 前缀 / 变体后缀，得到可匹配的 id。"""
    if not model:
        return ""
    m = str(model).strip().lower()
    # 'opencode-go/deepseek-v4-flash' -> 'deepseek-v4-flash'
    m = re.sub(r'^[a-z0-9_.-]+/', '', m)
    return m


def price_for(model):
    """返回 (price_dict, matched_key)。按最长前缀匹配。"""
    m = normalize_model(model)
    if not m:
        return DEFAULT_PRICE, ""
    best = None
    for key in PRICES:
        if m == key:
            return PRICES[key], key
        if m.startswith(key):
            if best is None or len(key) > len(best):
                best = key
    if best:
        return PRICES[best], best
    return DEFAULT_PRICE, ""


def estimate_cost(model, input_tokens, output_tokens, cache_read=0, cache_write=0):
    """按模型单价估算成本（USD）。input 不含 cache_read（与各数据源口径一致）。"""
    price, _ = price_for(model)
    return round(
        (input_tokens * price["input"]
         + output_tokens * price["output"]
         + cache_read * price["cache_read"]
         + cache_write * price["cache_write"]) / 1e6,
        6,
    )
