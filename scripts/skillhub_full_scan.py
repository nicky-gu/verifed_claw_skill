#!/usr/bin/env python3
"""
Skillhub 全量技能安全扫描器 v3
- 自动下载技能 zip
- 用规则引擎扫描（与 skill-vetter 同样的 RED FLAGS）
- 按优先级排序：先扫描高下载量技能
- 输出结构化 JSON + Markdown 报告
"""
import json, os, re, sys, time, zipfile, io, urllib.request, tempfile, concurrent.futures, traceback

# ---- 配置 ----
INDEX_URL = "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/skills.json"
# 使用 lightmake.site API 作为主要下载源（覆盖全部 15k+ 技能）
# COS URL 只覆盖索引中的 50 个
DOWNLOAD_URL_TEMPLATE = "https://lightmake.site/api/v1/download?slug=%s"
SLUGS_FILE = "/tmp/skillhub_complete_slugs.json"
OUTPUT_DIR = os.path.expanduser("~/.openclaw/reports")
MAX_CONCURRENT = 8  # 并发下载数
MAX_TOTAL = 0        # 0 = 全部

# ---- 规则引擎 (与 skill-vetter RED FLAGS 对齐) ----

CRITICAL_RULES = [
    ("reverse_shell", r"nc\s+-[elp]", "反弹 shell 命令"),
    ("remote_exec_pipe", r"(curl|wget)\s+.*\|\s*(sh|bash|python|perl|ruby)", "下载并执行远程脚本"),
    ("ssh_key_theft", r"(cat|cp|scp|ssh-copy-id).*id_rsa|\.ssh/(id_|config|authorized)", "SSH 密钥窃取"),
    ("system_file_modify", r"/etc/(passwd|shadow|sudoers|crontab)|authorized_keys|systemctl\s+enable", "修改系统关键文件"),
    ("crypto_mining", r"stratum\+tcp|minerd|xmrig|cpuminer|cryptonight", "加密货币挖矿"),
    ("credential_exfil", r"curl.*\b(id_rsa|\.ssh|\.aws|\.env|credential|secret)\b", "凭证外传"),
    ("base64_payload", r"(base64|openssl).*-d.*\|\s*(sh|bash|eval|exec)", "Base64 解码并执行"),
]

HIGH_RULES = [
    ("unknown_external_url", r"https?://(?!github\.com|raw\.githubusercontent\.com|clawhub\.com|clawhub\.ai|skillhub|openclaw|cos\.ap-guangzhou\.myqcloud\.com|lightmake\.site|api\.openai\.com|api\.anthropic\.com|open-meteo\.com|wttr\.in|fonts\.googleapis\.com)", "连接未知外部服务器"),
    ("env_var_read", r"os\.environ\[|process\.env\.|\$\{[A-Z_]+[A-Z_0-9]*\}", "读取环境变量（可能含密钥）"),
    ("file_write_system", r"(writeFile|fs\.write|open\(.*['\"]w)|echo.*>.*(/etc|/var|/usr|/bin)", "写入系统目录"),
    ("unsafe_deserialize", r"(pickle\.loads|yaml\.load|eval\(|Function\()", "不安全的反序列化"),
    ("shell_config_modify", r"\.(bashrc|zshrc|profile|bash_profile)", "修改 Shell 配置文件"),
    ("obfuscated_channel", r"base64.*curl|xxd.*\|\s*nc|openssl.*base64", "混淆数据通道"),
    ("sudo_required", r"\bsudo\b", "需要 sudo 权限"),
    ("eval_with_input", r"(eval|exec)\s*.*(\$\(|request|input|response|user)", "用外部输入执行 eval/exec"),
]

MEDIUM_RULES = [
    ("systemd_service", r"systemd|launchd|init\.d|supervisor", "注册系统服务"),
    ("path_manipulation", r"PATH\s*=|export\s+PATH|PATH_PREFIX", "修改 PATH"),
    ("persistent_loop", r"(setInterval|while\s+True|while\s+true).*", "持久循环"),
    ("cron_job", r"crontab|cron\s", "定时任务"),
    ("large_file_scan", r"(os\.walk|glob\*|find\s+-exec).*-R|-r\b", "递归文件扫描"),
    ("npm_pip_install", r"(npm|pip|yarn)\s+install", "安装外部包"),
]

def scan_content(content, rules):
    """扫描文本内容，返回匹配的规则"""
    findings = []
    for rule_id, pattern, description in rules:
        try:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                start = max(0, m.start() - 30)
                end = min(len(content), m.end() + 30)
                context = content[start:end].replace('\n', ' ').replace('\r', '')[:120]
                findings.append({
                    "rule_id": rule_id,
                    "severity": description,
                    "pattern": pattern[:60],
                    "context": context,
                })
        except re.error:
            pass
    return findings

def audit_skill(slug, meta=None):
    """审计单个技能"""
    result = {
        "slug": slug,
        "name": (meta or {}).get("name", ""),
        "version": (meta or {}).get("version", ""),
        "status": "unknown",
        "risk_level": "UNKNOWN",
        "file_count": 0,
        "total_size": 0,
        "has_scripts": False,
        "has_hooks": False,
        "has_exec_directives": False,
        "suspicious_files": [],
        "critical": 0,
        "high": 0,
        "medium": 0,
        "findings": [],
        "error": None,
    }

    # 下载
    url = DOWNLOAD_URL_TEMPLATE % slug
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "skillhub-audit/3.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            zip_data = resp.read()
    except Exception as e:
        result["status"] = "download_failed"
        result["error"] = str(e)[:100]
        return result

    if len(zip_data) < 50:
        result["status"] = "empty"
        return result

    # 解压并扫描
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            all_content_parts = []
            for info in zf.infolist():
                fname = info.filename
                if fname.endswith('/') or fname.startswith('__MACOSX') or '/.git/' in fname:
                    continue
                result["file_count"] += 1
                result["total_size"] += info.file_size

                # 结构检查
                if fname.startswith("scripts/") or any(fname.endswith(ext) for ext in ['.sh','.py','.js','.mjs','.ts','.rb','.pl']):
                    result["has_scripts"] = True
                if fname.startswith("hooks/"):
                    result["has_hooks"] = True
                if any(k in fname.lower() for k in ['.env','secret','credential','token','private']):
                    result["suspicious_files"].append(fname)

                # 读取内容
                try:
                    content = zf.read(fname).decode("utf-8", errors="ignore")
                    all_content_parts.append(f"===FILE:{fname}===\n{content}")
                    if fname == "SKILL.md":
                        if re.search(r'\bexec\b|shell.*command|subprocess|os\.system|child_process', content, re.I):
                            result["has_exec_directives"] = True
                except:
                    pass

            all_content = "\n".join(all_content_parts)

    except Exception as e:
        result["status"] = "unzip_failed"
        result["error"] = str(e)[:100]
        return result

    result["status"] = "audited"

    # 运行规则扫描
    c_findings = scan_content(all_content, CRITICAL_RULES)
    h_findings = scan_content(all_content, HIGH_RULES)
    m_findings = scan_content(all_content, MEDIUM_RULES)

    # 去重（同一规则同一文件只保留一个）
    def dedup(findings):
        seen = set()
        out = []
        for f in findings:
            key = f["rule_id"] + f["context"][:50]
            if key not in seen:
                seen.add(key)
                out.append(f)
        return out

    c_findings = dedup(c_findings)
    h_findings = dedup(h_findings)
    m_findings = dedup(m_findings)

    result["critical"] = len(c_findings)
    result["high"] = len(h_findings)
    result["medium"] = len(m_findings)
    result["findings"] = [
        {**f, "severity": "CRITICAL"} for f in c_findings
    ] + [
        {**f, "severity": "HIGH"} for f in h_findings
    ] + [
        {**f, "severity": "MEDIUM"} for f in m_findings
    ]

    # 风险等级
    if result["critical"] > 0:
        result["risk_level"] = "EXTREME"
    elif result["high"] > 0:
        result["risk_level"] = "HIGH"
    elif result["medium"] > 0:
        result["risk_level"] = "MEDIUM"
    else:
        result["risk_level"] = "LOW"

    return result

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 加载 slug 列表
    with open(SLUGS_FILE) as f:
        all_slugs = json.load(f)

    # 也加载索引（有 downloads/stars 信息）
    try:
        with urllib.request.urlopen(INDEX_URL, timeout=10) as resp:
            idx_data = json.loads(resp.read())
        idx_meta = {s["slug"]: s for s in idx_data.get("skills", [])}
    except:
        idx_meta = {}

    slugs = list(all_slugs.keys())
    if MAX_TOTAL > 0:
        slugs = slugs[:MAX_TOTAL]

    print(f"=== Skillhub 全量安全扫描 v3 ===")
    print(f"总技能数: {len(slugs)}")
    print(f"并发数: {MAX_CONCURRENT}")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 并发扫描
    results = []
    done = 0
    failed = 0
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        future_map = {}
        for slug in slugs:
            meta = all_slugs.get(slug, {})
            # 补充索引元数据
            if slug in idx_meta:
                meta["downloads"] = idx_meta[slug].get("downloads", 0)
                meta["stars"] = idx_meta[slug].get("stars", 0)
            future = executor.submit(audit_skill, slug, meta)
            future_map[future] = slug

        for future in concurrent.futures.as_completed(future_map):
            slug = future_map[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append({"slug": slug, "status": "error", "error": str(e)[:100], "risk_level": "UNKNOWN"})
                failed += 1

            done += 1
            if done % 200 == 0:
                elapsed = time.time() - start_time
                rate = done / elapsed
                eta = (len(slugs) - done) / rate if rate > 0 else 0
                print(f"  进度: {done}/{len(slugs)} ({done*100//len(slugs)}%) | "
                      f"{rate:.0f} skills/s | ETA: {eta/60:.0f}min")

    elapsed = time.time() - start_time
    print(f"\n扫描完成！耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"成功: {len([r for r in results if r['status'] == 'audited'])}")
    print(f"失败: {len([r for r in results if r['status'] != 'audited'])}")

    # 统计
    risk_counts = {}
    for r in results:
        rl = r.get("risk_level", "UNKNOWN")
        risk_counts[rl] = risk_counts.get(rl, 0) + 1

    print(f"\n风险分布:")
    for rl in ["EXTREME", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]:
        c = risk_counts.get(rl, 0)
        if c > 0:
            emoji = {"EXTREME":"⛔","HIGH":"🔴","MEDIUM":"🟡","LOW":"🟢","UNKNOWN":"❓"}[rl]
            print(f"  {emoji} {rl}: {c}")

    # 保存 JSON
    json_file = os.path.join(OUTPUT_DIR, f"skillhub-full-scan-{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(json_file, "w") as f:
        json.dump(results, f, ensure_ascii=False)
    print(f"\nJSON 报告: {json_file}")

    # 生成 Markdown 报告
    md_file = json_file.replace(".json", ".md")
    order = {"EXTREME":0,"HIGH":1,"MEDIUM":2,"LOW":3,"UNKNOWN":4}
    results.sort(key=lambda r: (order.get(r["risk_level"],5), r["slug"]))

    with open(md_file, "w") as f:
        f.write(f"# Skillhub 全量技能安全扫描报告\n\n")
        f.write(f"**扫描时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**扫描范围**: {len(results)} 个技能\n\n")
        f.write(f"**扫描耗时**: {elapsed:.0f}s\n\n")
        f.write("## 风险概览\n\n")
        f.write("| 风险等级 | 数量 | 占比 |\n|---------|------|------|\n")
        for rl in ["EXTREME","HIGH","MEDIUM","LOW","UNKNOWN"]:
            c = risk_counts.get(rl, 0)
            emoji = {"EXTREME":"⛔","HIGH":"🔴","MEDIUM":"🟡","LOW":"🟢","UNKNOWN":"❓"}[rl]
            pct = c*100//len(results) if results else 0
            f.write(f"| {emoji} {rl} | {c} | {pct}% |\n")

        f.write("\n---\n\n")

        # EXTREME 详情
        extreme = [r for r in results if r["risk_level"] == "EXTREME"]
        if extreme:
            f.write("## ⛔ EXTREME — 建议禁止安装\n\n")
            for r in extreme:
                f.write(f"### `{r['slug']}`\n")
                f.write(f"- 发现: 🔴×{r['critical']} 🟠×{r['high']} 🟡×{r['medium']}\n")
                f.write(f"- 文件数: {r['file_count']} | 大小: {r['total_size']} bytes\n")
                if r.get("has_scripts"): f.write("- ⚠️ 包含可执行脚本\n")
                if r.get("has_hooks"): f.write("- ⚠️ 包含 hooks\n")
                f.write("\n<details><summary>📋 CRITICAL 发现</summary>\n\n")
                for fi in r["findings"]:
                    if fi["severity"] == "CRITICAL":
                        ctx = fi["context"][:100].replace("|","\\|")
                        f.write(f"- **{fi['severity']}** [{fi['rule_id']}] `{ctx}`\n")
                f.write("\n</details>\n\n")

        # HIGH 详情
        high = [r for r in results if r["risk_level"] == "HIGH"]
        if high:
            f.write(f"## 🔴 HIGH — 需安全审批 ({len(high)} 个)\n\n")
            f.write("| 技能 | 文件 | CRITICAL | HIGH | MEDIUM | 脚本 |\n")
            f.write("|------|------|----------|------|--------|------|\n")
            for r in high:
                scripts = "✅" if r.get("has_scripts") else ""
                f.write(f"| `{r['slug']}` | {r['file_count']} | {r['critical']} | {r['high']} | {r['medium']} | {scripts} |\n")
            f.write("\n")

        # MEDIUM 摘要
        medium = [r for r in results if r["risk_level"] == "MEDIUM"]
        if medium:
            f.write(f"## 🟡 MEDIUM — 需谨慎 ({len(medium)} 个)\n\n")
            f.write(f"共 {len(medium)} 个技能，不逐一列出。\n\n")

        # LOW 统计
        low = [r for r in results if r["risk_level"] == "LOW"]
        f.write(f"## 🟢 LOW — 可安全安装 ({len(low)} 个)\n\n")

    print(f"Markdown 报告: {md_file}")

if __name__ == "__main__":
    main()
