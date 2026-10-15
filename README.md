# Token-消耗看板

跨 Agent **真实 Token 数** 采集与展示（无价格估算、无正文字符估算）。

## 计费口径（契约，改动前必读）

| 指标 | 口径 | 说明 |
| --- | --- | --- |
| **今日** | 本地自然日 0 点起（非滚动 24h） | 全局视图与筛选视图一致 |
| **本周** | 滚动 7 天 | |
| **累计** | 全部事件 | |
| **消耗 Tokens** | `input(新输入) + output` | **不含缓存**；缓存单独显示为"省流" |
| **input 语义** | 新输入，**不含 cache_read** | Codex/Grok/Antigravity 源端 input 含缓存，采集时已拆分 |
| **成本** | 真实 cost 优先（Grok/网关/手动上报）；其余为估算，表格行以 `≈` 标识 | 卡片标题均标注"估算" |

> 防回归：以上契约由 `test_billing_accuracy.py` 断言锁定（含前端卡片口径检查）。

## 启动

```bash
cd projects/token-dashboard
python server.py
# http://127.0.0.1:8712
```

- 一键启动 / 开机自启：双击 `start_dashboard.bat`（自动防重复；复制到 `shell:startup` 文件夹可开机自启）
- 服务器重启电脑后需重新启动（见上）

## 各 Agent 准确性

| Agent | 数据源 | 状态 |
| --- | --- | --- |
| OpenCode | `opencode.db` 字段（08-08 起才有数据） | 可对账，高 |
| Codex CLI/VSCode | `state_5.sqlite` + rollout JSONL | 可对账，高 |
| Grok | `updates.jsonl` 每轮 usage | 可对账，高 |
| ZCode | `~/.zcode/cli/db/db.sqlite` 的 `model_usage`（每请求 usage，实时落库） | 可对账，高 |
| Hermes | `session_model_usage`；cwd 空时扫消息路径 | 高 |
| Antigravity Pro | 仅 task-log 内 Google `inputTokens/outputTokens` | **有 log 才准**；Pro 多数会话本地不落 token |
| 手动上报 | `report.py` | 你填多少算多少 |

### Antigravity Pro 说明

Pro 登录 **不会** 在本地生成完整账单。实测：60+ 会话里只有少数 task-log 带真实 usage。  
看板策略：

- 抠到真实 usage → 计入（不因 cwd 缺失丢弃）
- 抠不到 → **不计**（不估算）
- 需要完整 Pro 用量 → 从 Google AI / Cloud 用量页导出后 `report.py` 补录

## 对账

```bash
python reconcile.py          # OpenCode / Codex / Grok / ZCode / Hermes 与源数据交叉验证
python test_billing_accuracy.py
```

## 手动补录

```bash
python report.py --agent Antigravity --model gemini-3.6-flash --input 12345 --output 678 --note "Pro 账单"
```

与自动源同名时显示为 `手动·Agent`，防双计。

## 统计范围

- 默认：Work space 目录（Antigravity 有真实 usage 且 cwd 未知时仍计入）
- 全部目录：`python server.py --all-agents`
