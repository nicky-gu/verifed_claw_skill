# Skillhub 全量技能安全审计报告

**扫描时间**: 2026-04-10 22:52 CST

**扫描范围**: 15,269 个技能（成功审计 15,259 个）

**扫描耗时**: 19.4 分钟

## 风险概览

| 风险等级 | 数量 | 占比 |
|---------|------|------|
| ⛔ EXTREME | 698 | 4.6% |
| 🔴 HIGH | 11380 | 74.5% |
| 🟡 MEDIUM | 764 | 5.0% |
| 🟢 LOW | 2417 | 15.8% |
| ❓ UNKNOWN | 10 | 0.1% |

## ⛔ EXTREME — Top 30

| 技能 | CRITICAL | HIGH | MEDIUM | 文件数 |
|------|----------|------|--------|--------|
| `claw-audit` | 80 | 520 | 87 | 32 |
| `reefwatch` | 60 | 40 | 62 | 42 |
| `agent-lottery` | 45 | 14 | 2 | 7 |
| `lobsterguard` | 43 | 448 | 234 | 23 |
| `guard-scanner` | 33 | 442 | 87 | 115 |
| `everclaw-inference` | 32 | 815 | 201 | 199 |
| `linux-patcher` | 26 | 94 | 25 | 14 |
| `vext-shield` | 26 | 34 | 66 | 35 |
| `clauditor` | 25 | 63 | 147 | 24 |
| `skill-security-audit` | 25 | 32 | 8 | 4 |
| `ecap-security-auditor` | 23 | 270 | 105 | 37 |
| `ssh-essentials` | 19 | 7 | 5 | 2 |
| `hostinger-vps-mcp-tools` | 19 | 64 | 16 | 22 |
| `clawguard-detector` | 19 | 13 | 7 | 6 |
| `aliyun-clawscan` | 18 | 22 | 4 | 5 |
| `sysadmin-toolbox` | 17 | 488 | 22 | 8 |
| `slowmist-agent-security` | 17 | 39 | 29 | 16 |
| `goplus-agentguard` | 16 | 22 | 50 | 15 |
| `monero-mining-101` | 16 | 7 | 0 | 3 |
| `ctct-security-patrol-wb` | 16 | 127 | 38 | 3 |
| `ssh-tunnel` | 15 | 3 | 4 | 2 |
| `jugaad-clawguard` | 14 | 159 | 28 | 28 |
| `skill-shield` | 14 | 25 | 8 | 6 |
| `safe-exec-0-3-2` | 14 | 82 | 48 | 37 |
| `surrealdb-knowledge-graph-memory` | 14 | 129 | 89 | 34 |
| `ansible-skill` | 14 | 26 | 45 | 21 |
| `clawvet` | 14 | 354 | 13 | 93 |
| `one-skill-to-rule-them-all` | 13 | 17 | 10 | 2 |
| `clawdbot-security-suite` | 13 | 82 | 25 | 17 |
| `molt-market` | 12 | 10 | 0 | 3 |

## 📊 说明

- **EXTREME**: 发现 CRITICAL 级别规则匹配（反弹 shell、凭据窃取、挖矿等）
- **HIGH**: 发现 HIGH 级别规则匹配（外部 URL、环境变量读取、eval/exec 等）
- **MEDIUM**: 发现 MEDIUM 级别规则匹配（系统服务、PATH 修改等）
- **LOW**: 未发现明显风险模式
- HIGH 标签包含大量误报（文档中提及 eval/外部 URL），建议对高下载量技能优先人工审查
