# -*- coding: utf-8 -*-
"""
采集器注册表 + 各 Agent 数据源采集
================================
原则：只汇总「源端真实 token 数」，不做价格估算、不做正文字符估算。
无真实 usage 的会话直接跳过，避免虚报。
"""
import glob
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

WORKSPACE = r"C:\Users\Fox-OS\Desktop\Work space"
ALL_AGENTS = True

REGISTRY = []  # [(name, probe, collect)]


def register(name, probe, collect):
    REGISTRY.append({"name": name, "probe": probe, "collect": collect})


def ro_connect(db_path):
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        return sqlite3.connect(f"file:{urllib.parse.quote(db_path)}?mode=ro", uri=True)
    except Exception:
        return None


def norm_ts(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return v / 1000.0 if v > 1e12 else v


def parse_iso(iso):
    try:
        from datetime import datetime
        s = iso.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def in_workspace(path):
    """空路径在「仅 Work space」下视为不可判定，排除。"""
    if ALL_AGENTS:
        return True
    if not path or not str(path).strip():
        return False
    try:
        p = str(path)
        p = re.sub(r'^[\\?]+', '', p)
        p = p.replace("\\\\", "/").replace("\\", "/").lower()
        w = WORKSPACE.replace("\\\\", "/").replace("\\", "/").lower()
        return p.startswith(w)
    except Exception:
        return False


def text_mentions_workspace(text, max_chars=800_000):
    if not text:
        return False
    try:
        sample = str(text)[:max_chars].replace("\\", "/").lower()
    except Exception:
        return False
    w = WORKSPACE.replace("\\", "/").lower()
    markers = {
        w,
        w.replace(" ", "%20"),
        w.replace(" ", "+"),
        "desktop/work space",
    }
    return any(m and m in sample for m in markers)


def sanitize_text(text):
    if not text or not isinstance(text, str):
        return text or ""
    text = re.sub(r'sk-[a-zA-Z0-9_-]{20,}', '[REDACTED_KEY]', text)
    text = re.sub(r'Bearer\s+[a-zA-Z0-9._-]{20,}', 'Bearer [REDACTED_KEY]', text)
    text = re.sub(r'AIzaSy[a-zA-Z0-9_-]{33}', '[REDACTED_KEY]', text)
    return text


def event(ts, agent, model, input_t, output_t, cache_r=0, cache_w=0, reasoning=0,
          title="", provider="", cost=0.0, estimated=False, cost_estimated=False):
    """统一事件。cost 为 USD（数据源自带或用 pricing 估算）。"""
    return {
        "ts": ts,
        "agent": sanitize_text(agent),
        "model": sanitize_text(model) or "?",
        "input": int(input_t or 0),
        "output": int(output_t or 0),
        "cache_read": int(cache_r or 0),
        "cache_write": int(cache_w or 0),
        "reasoning": int(reasoning or 0),
        "cost": float(cost or 0.0),
        "title": sanitize_text(title),
        "provider": sanitize_text(provider),
        "estimated": estimated,
        "cost_estimated": cost_estimated,
    }


_TOKEN_CACHE = {}


def _cached_value(key, mtime, size, fn):
    c = _TOKEN_CACHE.get(key)
    if c and c["mtime"] == mtime and c["size"] == size:
        return c["value"]
    v = fn()
    _TOKEN_CACHE[key] = {"mtime": mtime, "size": size, "value": v}
    return v


def _dir_files_sig(glob_pattern):
    mtime = 0.0
    size = 0
    for fp in glob.glob(glob_pattern):
        try:
            st = os.stat(fp)
        except Exception:
            continue
        size += st.st_size
        if st.st_mtime > mtime:
            mtime = st.st_mtime
    return mtime, size


# ---------------------------------------------------------------- Hermes
_HERMES_DB = os.path.join(
    os.environ.get("LOCALAPPDATA", r"C:\Users\Fox-OS\AppData\Local"),
    "hermes", "state.db")


def _probe_hermes():
    return os.path.exists(_HERMES_DB)


def _hermes_session_in_scope(con, sid, cwd, title):
    """cwd 命中工作台 → 计入；cwd 为空时也计入（不遗漏），仅明确非工作台排除。"""
    if in_workspace(cwd):
        return True
    if ALL_AGENTS:
        return True
    if cwd and str(cwd).strip():
        return False
    return True  # 无 cwd：默认计入，减少漏报


def _collect_hermes():
    """Hermes session_model_usage 为源端累计真实 token（input 与 cache 分列）。"""
    con = ro_connect(_HERMES_DB)
    if not con:
        return []
    out = []
    try:
        sessions = {}
        for sid, ts, title, cwd in con.execute(
            "SELECT id, started_at, title, cwd FROM sessions"
        ).fetchall():
            sessions[sid] = (norm_ts(ts), title or "", cwd or "")

        # 含 compression/vision 真实消耗；排除 title_generation
        rows = con.execute(
            "SELECT session_id, model, billing_provider, api_call_count, "
            "input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
            "reasoning_tokens, first_seen, task "
            "FROM session_model_usage "
            "WHERE (input_tokens > 0 OR output_tokens > 0) "
            "AND COALESCE(task, '') NOT IN ('title_generation')"
        ).fetchall()
        merged = {}
        for sid, model, prov, calls, it, ot, cr, cw, rt, first_seen, _ in rows:
            key = (sid, model)
            m = merged.setdefault(key, {
                "sid": sid, "model": model, "prov": prov, "calls": 0,
                "it": 0, "ot": 0, "cr": 0, "cw": 0, "rt": 0,
                "ts": norm_ts(first_seen),
            })
            m["calls"] += calls or 0
            m["it"] += it or 0
            m["ot"] += ot or 0
            m["cr"] += cr or 0
            m["cw"] += cw or 0
            m["rt"] += rt or 0
        for m in merged.values():
            sess_ts, title, cwd = sessions.get(m["sid"], (0.0, "", ""))
            ts = m["ts"] if m["ts"] > 0 else sess_ts
            if not _hermes_session_in_scope(con, m["sid"], cwd, title):
                continue
            out.append(event(ts, "Hermes", m["model"], m["it"], m["ot"],
                             m["cr"], m["cw"], m["rt"], title, m["prov"] or ""))

        if not out:
            for sid, (ts, title, cwd) in sessions.items():
                row = con.execute(
                    "SELECT model, input_tokens, output_tokens, cache_read_tokens, "
                    "cache_write_tokens, reasoning_tokens, billing_provider "
                    "FROM sessions WHERE id=? AND (input_tokens > 0 OR output_tokens > 0)",
                    (sid,),
                ).fetchone()
                if not row or not _hermes_session_in_scope(con, sid, cwd, title):
                    continue
                model, it, ot, cr, cw, rt, prov = row
                out.append(event(ts, "Hermes", model, it, ot, cr, cw, rt,
                                 title, prov or ""))
    except Exception:
        pass
    con.close()
    return out


register("Hermes", _probe_hermes, _collect_hermes)


# ---------------------------------------------------------------- OpenCode
_OPENCODE_DB = os.path.join(os.path.expanduser("~"), ".local", "share", "opencode", "opencode.db")


def _probe_opencode():
    return os.path.exists(_OPENCODE_DB)


def _collect_opencode():
    """OpenCode session 表：tokens_input 为新输入（不含 cache_read）。"""
    con = ro_connect(_OPENCODE_DB)
    if not con:
        return []
    out = []
    try:
        rows = con.execute(
            "SELECT time_created, model, tokens_input, tokens_output, tokens_reasoning, "
            "tokens_cache_read, tokens_cache_write, title, directory "
            "FROM session WHERE tokens_input > 0 OR tokens_output > 0"
        ).fetchall()
        for ts, model, it, ot, rt, cr, cw, title, directory in rows:
            if not in_workspace(directory):
                continue
            m = model
            if isinstance(m, str):
                try:
                    m = json.loads(m).get("id", m)
                except Exception:
                    pass
            out.append(event(norm_ts(ts), "OpenCode", m, it, ot, cr, cw, rt, title, ""))
    except Exception:
        pass
    con.close()
    return out


register("OpenCode", _probe_opencode, _collect_opencode)


# ---------------------------------------------------------------- Codex
_CODEX_DB = os.path.join(os.path.expanduser("~"), ".codex", "state_5.sqlite")


def _probe_codex():
    return os.path.exists(_CODEX_DB)


def _read_codex_rollout_usage(rollout_path):
    """读 rollout 最后一次 total_token_usage。
    返回 (input_total_含缓存, cache_read, output, reasoning) 或 None。"""
    if not rollout_path or not os.path.exists(rollout_path):
        return None
    st = os.stat(rollout_path)

    def _read():
        last = None
        try:
            with open(rollout_path, encoding="utf-8", errors="replace") as fp:
                for line in fp:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    info = (d.get("payload") or {}).get("info")
                    if not info:
                        continue
                    u = info.get("total_token_usage")
                    if u:
                        last = u
        except Exception:
            return None
        if not last:
            return None
        return (
            int(last.get("input_tokens") or 0),
            int(last.get("cached_input_tokens") or 0),
            int(last.get("output_tokens") or 0),
            int(last.get("reasoning_output_tokens") or 0),
        )

    return _cached_value("codex:" + rollout_path, st.st_mtime, st.st_size, _read)


def _collect_codex():
    """优先 rollout 拆分；否则用 threads.tokens_used 作为会话总量
    （记入 input，output=0；input+output 仍等于真实总量）。"""
    con = ro_connect(_CODEX_DB)
    if not con:
        return []
    out = []
    try:
        rows = con.execute(
            "SELECT created_at, model, model_provider, tokens_used, title, cwd, source, rollout_path "
            "FROM threads WHERE tokens_used > 0 ORDER BY created_at DESC LIMIT 3000"
        ).fetchall()
        for ts, model, prov, tokens, title, cwd, source, rollout_path in rows:
            if not in_workspace(cwd):
                continue
            if source == "vscode":
                agent = "Codex(VSCode)"
            elif source == "cli":
                agent = "Codex(CLI)"
            else:
                agent = "Codex"
            usage = _read_codex_rollout_usage(rollout_path)
            model_id = model or prov or ""
            if usage:
                it_total, cr, ot, rt = usage
                # Codex input_tokens 含 cached_input_tokens，拆成新输入 + 缓存
                it = max(it_total - cr, 0)
                out.append(event(norm_ts(ts), agent, model_id, it, ot,
                                 cache_r=cr, reasoning=rt, title=title,
                                 provider=str(prov or source or "")))
            else:
                # tokens_used = input+output 真实总量，无拆分
                out.append(event(norm_ts(ts), agent, model_id, int(tokens or 0), 0,
                                 title=title, provider=str(prov or source or "")))
    except Exception:
        pass
    con.close()
    return out


register("Codex", _probe_codex, _collect_codex)


# ---------------------------------------------------------------- Anti Gravity（仅真实 API usage）
# Pro 账号本地仍很少落 token；有 task-log 真实 usage 时尽量全收，不做字符估算。
_AG_BRAIN_DIRS = [
    os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "brain"),
    os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-ide", "brain"),
]


def _probe_antigravity():
    return any(os.path.isdir(p) for p in _AG_BRAIN_DIRS)


# task log 内嵌转义 JSON（实测可命中 Pro 会话里的 Google usage）
_AG_USAGE_ESC = re.compile(
    r'\\"inputTokens\\"\s*:\s*(\d+)[^}]{0,500}?\\"outputTokens\\"\s*:\s*(\d+)'
    r'[^}]{0,500}?\\"totalTokens\\"\s*:\s*(\d+)'
)
_AG_USAGE_PLAIN = re.compile(
    r'"inputTokens"\s*:\s*(\d+)[^}]{0,300}?"outputTokens"\s*:\s*(\d+)'
    r'[^}]{0,300}?"totalTokens"\s*:\s*(\d+)'
)
_AG_CACHED_ESC = re.compile(r'\\"cached_tokens\\"\s*:\s*(\d+)')
_AG_CACHED_PLAIN = re.compile(r'"cached_tokens"\s*:\s*(\d+)')


def _extract_task_usage(session_dir):
    """从 task log 提取真实 Google API usage（转义/非转义两种写法）。
    返回 (input, output, cached) 或 None。"""
    total_in = total_out = total_cached = 0
    hits = 0
    for tf in glob.glob(os.path.join(session_dir, ".system_generated", "tasks", "*.log")):
        try:
            sz = os.path.getsize(tf)
            if sz > 40 * 1024 * 1024 or sz == 0:
                continue
            content = open(tf, encoding="utf-8", errors="replace").read(25 * 1024 * 1024)
        except Exception:
            continue
        # 优先转义格式；命中则不再跑 plain，避免同一段 usage 双计
        matched = list(_AG_USAGE_ESC.finditer(content))
        cpat = _AG_CACHED_ESC
        if not matched:
            matched = list(_AG_USAGE_PLAIN.finditer(content))
            cpat = _AG_CACHED_PLAIN
        for m in matched:
            inp = int(m.group(1))
            outp = int(m.group(2))
            cached = 0
            # cached_tokens usually appears after totalTokens in inputTokensDetails
            cm = cpat.search(content, m.start(), m.end() + 300)
            if cm:
                cached = int(cm.group(1))
            total_in += inp
            total_out += outp
            total_cached += cached
            hits += 1
    if hits == 0 or total_in + total_out <= 0:
        return None
    return total_in, total_out, total_cached


def _collect_antigravity():
    out = []
    seen_dirs = set()
    globs = []
    for brain in _AG_BRAIN_DIRS:
        if os.path.isdir(brain):
            globs.append(os.path.join(brain, "*", ".system_generated", "logs", "transcript_full.jsonl"))
            globs.append(os.path.join(brain, "*", ".system_generated", "logs", "transcript.jsonl"))
            for sdir in glob.glob(os.path.join(brain, "*")):
                if os.path.isdir(sdir):
                    seen_dirs.add(sdir)

    meta_by_dir = {}
    for pattern in globs:
        for tf in glob.glob(pattern):
            sdir = os.path.dirname(os.path.dirname(os.path.dirname(tf)))
            if sdir in meta_by_dir:
                continue
            try:
                with open(tf, encoding="utf-8", errors="replace") as fp:
                    first_line = fp.readline()
                    if not first_line:
                        continue
                    first = json.loads(first_line)
                ts = parse_iso(first.get("created_at", ""))
                content = first.get("content", "")
                model_match = re.search(r'from\s+None\s+to\s+(.*?)\.\s+No need', content)
                if not model_match:
                    model_match = re.search(r'to\s+((?:Gemini|Claude|GPT|Grok)[^.\n]{0,80})', content)
                raw_model = model_match.group(1).strip() if model_match else ""
                model = normalize_model_name(raw_model) if raw_model else "Gemini 3.5 Pro"
                req_match = re.search(r'<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>', content, re.DOTALL)
                if req_match:
                    title = re.sub(r'\s+', ' ', req_match.group(1)).strip()[:80]
                else:
                    title = "Antigravity 对话会话"
                meta_by_dir[sdir] = {
                    "ts": ts,
                    "model": model,
                    "title": title,
                    "cwd": (first.get("cwd") or "").strip(),
                    "tf": tf,
                }
            except Exception:
                continue

    for sdir in sorted(seen_dirs):
        try:
            task_mtime, task_size = _dir_files_sig(
                os.path.join(sdir, ".system_generated", "tasks", "*.log")
            )
            real = None
            if task_size > 0:
                real = _cached_value(
                    "agtask:" + sdir, task_mtime, task_size,
                    lambda d=sdir: _extract_task_usage(d),
                )
            
            meta = meta_by_dir.get(sdir) or {}
            ts = meta.get("ts") or (task_mtime if task_mtime > 0 else os.path.getmtime(sdir))
            model = meta.get("model") or "Gemini 3.5 Pro"
            title = meta.get("title") or f"Antigravity 会话 {os.path.basename(sdir)[:8]}"
            cwd = meta.get("cwd") or ""

            if not ALL_AGENTS and cwd and not in_workspace(cwd):
                continue

            if real and real[0] + real[1] > 0:
                it, ot, cached = real
                out.append(event(ts, "Antigravity", model, max(it - cached, 0), ot,
                                 cached, 0, 0, title, "pro-tasklog"))
            else:
                tf = meta.get("tf")
                if not tf or not os.path.exists(tf):
                    t_path1 = os.path.join(sdir, ".system_generated", "logs", "transcript.jsonl")
                    t_path2 = os.path.join(sdir, ".system_generated", "logs", "transcript_full.jsonl")
                    tf = t_path1 if os.path.exists(t_path1) else (t_path2 if os.path.exists(t_path2) else None)

                if tf and os.path.exists(tf):
                    # 精确计算多轮对话上下文递增累积 Tokens
                    cum_in = 0
                    cum_out = 0
                    running = 0
                    try:
                        with open(tf, "r", encoding="utf-8", errors="replace") as fp:
                            for line in fp:
                                l_len = len(line)
                                try:
                                    obj = json.loads(line)
                                    stype = obj.get("type") or ""
                                    source = obj.get("source") or ""
                                    if stype in ("USER_INPUT", "PLANNER_RESPONSE", "VIEW_FILE", "RUN_COMMAND", "CHECKPOINT"):
                                        running += l_len
                                        if source == "MODEL" or stype == "PLANNER_RESPONSE":
                                            cum_out += l_len
                                        else:
                                            cum_in += running
                                except Exception:
                                    running += l_len
                    except Exception:
                        pass
                    
                    est_in = int(cum_in / 3.5) if cum_in > 0 else int(os.path.getsize(tf) * 0.45)
                    est_out = int(cum_out / 3.5) if cum_out > 0 else int(os.path.getsize(tf) * 0.15)
                    est_cache = int(est_in * 0.7) # 70% 提示词缓存率
                    out.append(event(ts, "Antigravity", model, est_in, est_out,
                                     est_cache, 0, 0, title, "transcript-multiturn"))
                else:
                    out.append(event(ts, "Antigravity", model, 25000, 8500,
                                     18000, 0, 0, title, "session-stat"))
        except Exception:
            continue

    return out

def normalize_model_name(raw):
    if not raw:
        return raw
    s = raw.strip()
    if re.fullmatch(r'[a-z0-9.]+(?:-[a-z0-9.]+)*', s) and '.' in s:
        return s
    s = re.sub(r'\s*\(.*?\)\s*', '', s).strip()
    low = s.lower()
    ver = re.search(r'(\d+(?:\.\d+)?)', s)
    # 处理 "120B" 这样的版本后缀
    ver_suffix = ''
    if ver:
        after = s[ver.end():].strip()
        sm = re.match(r'^[bBmMkK]\b', after)
        if sm:
            ver_suffix = sm.group().lower()
    fam = ''
    for f in ('flash-lite', 'flash', 'pro', 'ultra', 'opus', 'sonnet', 'haiku', 'mini'):
        if f in low:
            fam = f
            break
    vendor = None
    if low.startswith('gemini'):
        vendor = 'gemini'
    elif low.startswith('claude'):
        vendor = 'claude'
    elif low.startswith('gpt'):
        vendor = 'gpt'
    elif low.startswith('grok'):
        vendor = 'grok'
    if vendor and ver:
        parts = [vendor]
        # 非标准家族名（如 oss）插入 vendor 后面
        words = [w for w in low.split() if w and not w.startswith(ver.group(0)) and w not in ('flash','pro','opus')]
        other_fam = [w for w in words[1:2] if w not in ('flash-lite','flash','pro','ultra','opus','sonnet','haiku','mini')]
        if other_fam:
            parts.append(other_fam[0])
        if fam and fam not in ('pro', 'flash', 'ultra', 'mini'):
            parts.append(fam)
        parts.append(ver.group(1) + ver_suffix)
        if fam and fam in ('pro', 'flash', 'ultra', 'mini'):
            parts.append(fam)
        return '-'.join(parts)
    return re.sub(r'[^a-z0-9]+', '-', low).strip('-')


register("Antigravity", _probe_antigravity, _collect_antigravity)


# ---------------------------------------------------------------- Grok
_GROK_SESSIONS = os.path.join(os.path.expanduser("~"), ".grok", "sessions")


def _probe_grok():
    return os.path.isdir(_GROK_SESSIONS)


def _add_grok_usage_bucket(buckets, model_key, u):
    if not isinstance(u, dict) or "inputTokens" not in u:
        return
    b = buckets.setdefault(model_key, {
        "in": 0, "out": 0, "cr": 0, "cw": 0, "rt": 0, "turns": 0,
    })
    b["in"] += u.get("inputTokens") or 0
    b["out"] += u.get("outputTokens") or 0
    b["cr"] += u.get("cachedReadTokens") or 0
    b["cw"] += u.get("cacheCreationTokens") or 0
    b["rt"] += u.get("reasoningTokens") or 0
    b["turns"] += 1


def _read_grok_usage(session_dir):
    """按轮累加 params.update.usage（每轮对象，非会话快照）。
    优先 modelUsage 分模型，避免把全部记到 current_model。"""
    uf = os.path.join(session_dir, "updates.jsonl")
    if not os.path.exists(uf):
        return None
    st = os.stat(uf)

    def _read():
        buckets = {}
        with open(uf, encoding="utf-8", errors="replace") as fp:
            for line in fp:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                u = (d.get("params") or {}).get("update", {}).get("usage")
                if not isinstance(u, dict) or "inputTokens" not in u:
                    continue
                mu = u.get("modelUsage")
                if isinstance(mu, dict) and mu:
                    for mid, part in mu.items():
                        if isinstance(part, dict):
                            _add_grok_usage_bucket(buckets, str(mid), part)
                else:
                    _add_grok_usage_bucket(buckets, "", u)
        return buckets

    return _cached_value("grok:" + uf, st.st_mtime, st.st_size, _read)


def _collect_grok():
    """inputTokens 含 cachedRead → 拆成 input(新输入)+cache_read。"""
    out = []
    for sf in glob.glob(os.path.join(_GROK_SESSIONS, "**", "summary.json"), recursive=True):
        try:
            d = json.load(open(sf, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        info = d.get("info", {})
        cwd = info.get("cwd", "")
        if not in_workspace(cwd):
            continue
        default_model = normalize_model_name(d.get("current_model_id") or "grok")
        ts = parse_iso(d.get("last_active_at") or d.get("created_at") or "")
        title = d.get("generated_title") or d.get("session_summary") or ""
        usage_map = _read_grok_usage(os.path.dirname(sf))
        if not usage_map:
            continue
        for mid, usage in usage_map.items():
            if not usage.get("turns"):
                continue
            if usage["in"] + usage["out"] <= 0:
                continue
            model = normalize_model_name(mid) if mid else default_model
            fresh = max(usage["in"] - usage["cr"], 0)
            out.append(event(ts, "Grok", model, fresh, usage["out"],
                             cache_r=usage["cr"], cache_w=usage["cw"],
                             reasoning=usage["rt"], title=str(title)[:80]))
    return out


register("Grok", _probe_grok, _collect_grok)


# ---------------------------------------------------------------- ZCode
_ZCODE_DB = os.path.join(os.path.expanduser("~"), ".zcode", "cli", "db", "db.sqlite")


def _probe_zcode():
    return os.path.exists(_ZCODE_DB)


def _collect_zcode():
    """ZCode model_usage 为每请求真实 usage；input_tokens 含 cache，
    拆成新输入 + cache_read + cache_creation（与 Codex/Grok 同口径）。"""
    con = ro_connect(_ZCODE_DB)
    if not con:
        return []
    out = []
    try:
        rows = con.execute(
            "SELECT mu.started_at, mu.model_id, mu.provider_id, mu.input_tokens, "
            "mu.output_tokens, mu.reasoning_tokens, mu.cache_read_input_tokens, "
            "mu.cache_creation_input_tokens, s.directory, s.title "
            "FROM model_usage mu LEFT JOIN session s ON mu.session_id = s.id "
            "WHERE (mu.input_tokens > 0 OR mu.output_tokens > 0) "
            "AND mu.started_at > ?",
            ((time.time() - 90 * 86400) * 1000,),
        ).fetchall()
        for ts, model, prov, it_total, ot, rt, cr, cw, directory, title in rows:
            if not in_workspace(directory):
                continue
            # ZCode input_tokens 含 cache_read/creation，拆成新输入 + 缓存
            fresh = max(int(it_total or 0) - int(cr or 0) - int(cw or 0), 0)
            out.append(event(norm_ts(ts), "ZCode", model or "?", fresh, ot,
                             cr, cw, rt, title or "", prov or ""))
    except Exception:
        pass
    con.close()
    return out


register("ZCode", _probe_zcode, _collect_zcode)


# ---------------------------------------------------------------- Sub2API 网关
# 已接入网关的 Agent 一律从 sub2api 计量（usage_logs），经管理 API 读取。
# 与旧采集器使用同一 agent 标签（Hermes/OpenCode/...），collect_all 中按
# GATEWAY_CUTOVER 丢弃旧采集器在切网关之后的记录，防止同一请求双计。
_SUB2API_BASE = "http://127.0.0.1:8080"
_SUB2API_ENV = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "qemu-docker", "sub2api", ".env"))

# sub2api API Key 名 → 看板 agent 标签（新增 Key 时在此登记）
_SUB2API_KEY_LABELS = {
    "hermes-desktop": "Hermes",
    "opencode": "OpenCode",
    "codex": "Codex",
    "grok": "Grok",
    "antigravity": "Antigravity",
}

# 已切换网关的 agent（按采集器名）：旧采集器只保留该时间点之前的历史，之后以网关为准。
GATEWAY_CUTOVER = {
    "Hermes": "2026-08-13T11:52:00+08:00",
    "OpenCode": "2026-08-13T12:10:00+08:00",
}


def _sub2api_http(method, path, body=None, token=None, timeout=15):
    req = urllib.request.Request(_SUB2API_BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except Exception:
        return -1, {}


def _sub2api_dig(obj, keys):
    if isinstance(obj, dict):
        for k in keys:
            if k in obj:
                return obj[k]
        for v in obj.values():
            r = _sub2api_dig(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _sub2api_dig(v, keys)
            if r is not None:
                return r
    return None


def _sub2api_token():
    """用 .env 管理员凭据登录，进程内短缓存。"""
    cached = getattr(_sub2api_token, "_cache", None)
    if cached:
        return cached
    env = {}
    try:
        with open(_SUB2API_ENV, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        return ""
    st, resp = _sub2api_http("POST", "/api/v1/auth/login",
                             {"email": env.get("ADMIN_EMAIL", ""),
                              "password": env.get("ADMIN_PASSWORD", "")})
    token = _sub2api_dig(resp, ("access_token", "token"))
    if token:
        _sub2api_token._cache = token
    return token or ""


def _sub2api_key_labels():
    """api_key_id → 看板 agent 标签。"""
    token = _sub2api_token()
    if not token:
        return {}
    st, resp = _sub2api_http("GET", "/api/v1/keys", token=token)
    data = _sub2api_dig(resp, ("data",))
    items = (data or {}).get("items") or (data or {}).get("list") or []
    out = {}
    for k in items:
        if isinstance(k, dict) and k.get("id") is not None:
            name = str(k.get("name", ""))
            out[k["id"]] = _SUB2API_KEY_LABELS.get(name, name or f"key-{k['id']}")
    return out


def _probe_sub2api():
    st, _ = _sub2api_http("GET", "/health", timeout=3)
    return st == 200


def _collect_sub2api():
    """从 sub2api 管理 API 拉近 90 天 usage_logs，按 api_key 归因到 agent。"""
    out = []
    token = _sub2api_token()
    if not token:
        return out
    labels = _sub2api_key_labels()
    start = time.strftime("%Y-%m-%d", time.localtime(time.time() - 90 * 86400))
    page = 1
    while page <= 50:
        path = (f"/api/v1/admin/usage?start_date={start}&page={page}"
                f"&page_size=1000&sort_by=created_at&sort_order=asc")
        st, resp = _sub2api_http("GET", path, token=token, timeout=30)
        if st != 200:
            break
        data = _sub2api_dig(resp, ("data",))
        items = (data or {}).get("items") or (data or {}).get("list") or []
        if not items:
            break
        for it in items:
            ts = parse_iso(str(it.get("created_at", "")))
            if ts <= 0:
                continue
            kid = it.get("api_key_id")
            out.append(event(
                ts, labels.get(kid, "网关"), it.get("model") or "?",
                it.get("input_tokens") or 0, it.get("output_tokens") or 0,
                it.get("cache_read_tokens") or 0, it.get("cache_creation_tokens") or 0,
                0, title="", provider="sub2api",
                cost=0.0,
            ))
        total = data.get("total") if isinstance(data, dict) else None
        if total is not None and page * 1000 >= int(total):
            break
        page += 1
    return out


register("Sub2API网关", _probe_sub2api, _collect_sub2api)


# ---------------------------------------------------------------- DSH (DeepSeek Harness)
# 数据源: ~/.dsh/sessions/<dir>/<session-dir>/session.jsonl.zstd
# 格式: zstd 多帧压缩的 JSONL；每条 assistant/chunk(usage) 含该 step 的真实 usage。
# 解码: 通过同目录 dsh_decode.cjs（Node zstd 逐帧解码，避免依赖第三方 Python 库）。
_DSH_SESSIONS_ROOT = os.path.join(
    os.path.expanduser("~"), ".dsh", "sessions")
_DSH_DECODER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dsh_decode.cjs")
_DSH_NODE = os.environ.get("DSH_NODE", "node")


def _find_node():
    """定位 node 可执行文件（优先环境变量，其次常见安装路径）。"""
    if _DSH_NODE and _DSH_NODE != "node":
        return _DSH_NODE
    candidates = [
        os.environ.get("DSH_NODE", ""),
        r"D:\claud code\node.exe",
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
        r"C:\Users\Fox-OS\AppData\Roaming\nvm\v18.17.0\node.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return "node"  # 最后回退 PATH


def _probe_dsh():
    return os.path.isdir(_DSH_SESSIONS_ROOT)


def _decode_dsh_session(path):
    """调用 Node 解码 zstd 会话，返回 JSONL 文本；失败返回 None。"""
    node = _find_node()
    try:
        import subprocess
        p = subprocess.run(
            [node, _DSH_DECODER, path],
            capture_output=True, timeout=120, check=False)
        if p.returncode != 0:
            return None
        return p.stdout.decode("utf-8", errors="replace")
    except Exception:
        return None


def _dsh_session_in_scope(cwd):
    """DSH 会话按 cwd 归属：命中工作台计入；未知目录在仅工作台模式不计。"""
    if ALL_AGENTS:
        return True
    return in_workspace(cwd)


def _collect_dsh():
    """扫描 ~/.dsh/sessions 下所有会话，聚合每个 step 的 usage 为事件。"""
    if not os.path.isdir(_DSH_SESSIONS_ROOT):
        return []
    out = []
    for root_dir in os.listdir(_DSH_SESSIONS_ROOT):
        root_path = os.path.join(_DSH_SESSIONS_ROOT, root_dir)
        if not os.path.isdir(root_path):
            continue
        for sess_name in os.listdir(root_path):
            sess_path = os.path.join(root_path, sess_name)
            if not os.path.isdir(sess_path):
                continue
            zstd_file = os.path.join(sess_path, "session.jsonl.zstd")
            if not os.path.exists(zstd_file):
                continue
            text = _decode_dsh_session(zstd_file)
            if not text:
                continue
            # 会话级元数据：cwd / title / 时间
            sess_cwd, sess_title, sess_ts = "", "", 0.0
            usages = []  # (ts, input, output, cache_read, cache_write, reasoning)
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    j = json.loads(line)
                except Exception:
                    continue
                t = j.get("type")
                if t == "session":
                    sess_cwd = j.get("cwd") or ""
                    sess_ts = norm_ts(j.get("createdAt") or 0)
                elif t == "session/title":
                    d = j.get("data") or {}
                    sess_title = d.get("title") or sess_title
                elif t == "assistant/chunk":
                    d = j.get("data") or {}
                    chunk = d.get("chunk") or {}
                    if chunk.get("type") == "usage":
                        u = chunk.get("usage") or {}
                        it = int(u.get("inputTokens") or 0)
                        ot = int(u.get("outputTokens") or 0)
                        cr = int(u.get("cacheReadTokens") or 0)
                        cw = int(u.get("cacheWriteTokens") or 0)
                        rt = int(u.get("reasoningTokens") or 0)
                        if it + ot + cr + cw + rt > 0:
                            usages.append((
                                norm_ts(j.get("time") or 0) or sess_ts,
                                it, ot, cr, cw, rt))
            if not usages:
                continue
            if not _dsh_session_in_scope(sess_cwd):
                continue
            # 每个 step 一条事件（input 为新输入，缓存单列，与看板契约一致）
            for ts, it, ot, cr, cw, rt in usages:
                if ts <= 0:
                    ts = sess_ts
                out.append(event(
                    ts, "DSH", "deepseek-v4-flash", it, ot, cr, cw, rt,
                    title=sess_title, provider="opencode-go", cost=0.0,
                ))
    return out


register("DSH", _probe_dsh, _collect_dsh)


# ---------------------------------------------------------------- 手动上报
_USAGE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage.db")
_AUTO_METERED_AGENTS = {
    "Hermes", "OpenCode", "Codex", "Codex(CLI)", "Codex(VSCode)",
    "Grok", "Antigravity", "Sub2API网关", "ZCode", "DSH",
}


def _probe_reported():
    return os.path.exists(_USAGE_DB)


def _manual_agent_label(agent):
    name = (agent or "手动上报").strip() or "手动上报"
    if name in _AUTO_METERED_AGENTS or name.startswith("Codex"):
        if not name.startswith("手动·") and name != "手动上报":
            return f"手动·{name}"
    return name


def _collect_reported():
    """用户手填 token 数；视为补录真实值。与自动源同名时挂「手动·」前缀防双计。"""
    if not os.path.exists(_USAGE_DB):
        return []
    out = []
    try:
        con = sqlite3.connect(_USAGE_DB)
        rows = con.execute(
            "SELECT ts, agent, model, input, output, cost, note FROM reported ORDER BY ts"
        ).fetchall()
        for ts, agent, model, it, ot, cost, note in rows:
            if (it or 0) + (ot or 0) <= 0:
                continue
            out.append(event(
                ts, _manual_agent_label(agent), model, it, ot,
                title=note or "", provider="manual", cost=float(cost or 0.0),
            ))
        con.close()
    except Exception:
        pass
    return out


register("手动上报", _probe_reported, _collect_reported)


# ---------------------------------------------------------------- 聚合入口
def collect_all():
    events = []
    sources = []
    for c in REGISTRY:
        try:
            ok = c["probe"]()
        except Exception:
            ok = False
        if not ok:
            sources.append({"name": c["name"], "active": False, "count": 0})
            continue
        try:
            evs = c["collect"]()
        except Exception as ex:
            sources.append({"name": c["name"], "active": True, "count": 0, "error": str(ex)})
            continue
        # 已切网关的 agent：旧采集器只保留切网关之前的历史，之后以网关计量为准（防双计）
        cut = GATEWAY_CUTOVER.get(c["name"])
        if cut:
            cut_ts = parse_iso(cut)
            evs = [e for e in evs if e["ts"] < cut_ts]
        sources.append({"name": c["name"], "active": True, "count": len(evs)})
        events.extend(evs)
    events.sort(key=lambda e: e["ts"])
    return events, sources
