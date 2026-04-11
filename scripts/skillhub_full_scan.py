#!/usr/bin/env python3
"""
ClawHub 全量技能安全扫描器 v5
- Phase 1: lightmake.site (无速率限制, ~17k skills)
- Phase 2: clawhub.ai (30 req/min, ~20k skills, ~12h)
- Supports checkpoint resume
- Pre-computed source map for optimal ordering
"""
import json, os, re, sys, time, zipfile, io, urllib.request, threading

LIGHTMAKE_DOWNLOAD = "https://lightmake.site/api/v1/download?slug=%s"
CLAWHUB_DOWNLOAD = "https://clawhub.ai/api/v1/download?slug=%s"
SLUGS_FILE = os.environ.get("SLUGS_FILE", "/tmp/skillhub_complete_slugs.json")
SOURCE_MAP_FILE = "/tmp/slug_source_map.json"
ORDERED_SLUGS_FILE = "/tmp/ordered_slugs.json"
OUTPUT_DIR = os.environ.get("AUDIT_REPORT_DIR", os.path.expanduser("~/.openclaw/reports"))

class RateLimiter:
    def __init__(self, max_per_window, window_sec):
        self.max = max_per_window
        self.window = window_sec
        self.timestamps = []
        self.lock = threading.Lock()
    def acquire(self):
        while True:
            with self.lock:
                now = time.time()
                self.timestamps = [t for t in self.timestamps if now - t < self.window]
                if len(self.timestamps) < self.max:
                    self.timestamps.append(now)
                    return
                wait = self.window - (now - self.timestamps[0]) + 0.5
            time.sleep(wait)

clawhub_limiter = RateLimiter(28, 60)

def download_lightmake(slug):
    try:
        req = urllib.request.Request(LIGHTMAKE_DOWNLOAD % slug, headers={"User-Agent": "skillhub-audit/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        return data if len(data) > 50 else None
    except: return None

def download_clawhub(slug, version=""):
    url = CLAWHUB_DOWNLOAD % slug + (f"&version={version}" if version else "")
    for attempt in range(5):
        clawhub_limiter.acquire()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "clawhub/0.9.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            return data if len(data) > 50 else None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry = e.headers.get("retry-after")
                reset = e.headers.get("x-ratelimit-reset")
                if retry: wait = int(retry) + 2
                elif reset: wait = max(int(reset) - time.time() + 2, 5)
                else: wait = 65
                time.sleep(wait)
                continue
            break
        except: break
        break
    return None

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
    findings = []
    for rule_id, pattern, description in rules:
        try:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                s = max(0, m.start()-30); e = min(len(content), m.end()+30)
                ctx = content[s:e].replace('\n',' ').replace('\r','')[:120]
                findings.append({"rule_id":rule_id,"severity":description,"pattern":pattern[:60],"context":ctx})
        except: pass
    return findings

def audit_skill(slug, meta, use_clawhub=False):
    result = {"slug":slug,"name":meta.get("name",""),"version":meta.get("version",""),
              "downloads":meta.get("downloads",0),"stars":meta.get("stars",0),
              "status":"unknown","risk_level":"UNKNOWN","file_count":0,"total_size":0,
              "has_scripts":False,"has_hooks":False,"has_exec_directives":False,
              "suspicious_files":[],"critical":0,"high":0,"medium":0,"findings":[],"error":None,"source":""}
    version = meta.get("version","")
    
    if use_clawhub:
        zip_data = download_clawhub(slug, version)
        if zip_data: result["source"] = "clawhub"
    else:
        zip_data = download_lightmake(slug)
        if zip_data: result["source"] = "lightmake"
    
    if not zip_data:
        result["status"] = "download_failed"
        return result

    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            parts = []
            for info in zf.infolist():
                fn = info.filename
                if fn.endswith('/') or fn.startswith('__MACOSX') or '/.git/' in fn: continue
                result["file_count"] += 1; result["total_size"] += info.file_size
                if fn.startswith("scripts/") or any(fn.endswith(e) for e in ['.sh','.py','.js','.mjs','.ts','.rb','.pl']): result["has_scripts"] = True
                if fn.startswith("hooks/"): result["has_hooks"] = True
                if any(k in fn.lower() for k in ['.env','secret','credential','token','private']): result["suspicious_files"].append(fn)
                try:
                    c = zf.read(fn).decode("utf-8",errors="ignore")
                    parts.append(f"===FILE:{fn}===\n{c}")
                    if fn == "SKILL.md" and re.search(r'\bexec\b|shell.*command|subprocess|os\.system|child_process',c,re.I): result["has_exec_directives"] = True
                except: pass
    except Exception as e:
        result["status"] = "unzip_failed"; result["error"] = str(e)[:100]; return result

    result["status"] = "audited"
    cf = scan_content("\n".join(parts), CRITICAL_RULES)
    hf = scan_content("\n".join(parts), HIGH_RULES)
    mf = scan_content("\n".join(parts), MEDIUM_RULES)
    def dedup(fs):
        seen=set(); out=[]
        for f in fs:
            k=f["rule_id"]+f["context"][:50]
            if k not in seen: seen.add(k); out.append(f)
        return out
    cf,hf,mf = dedup(cf),dedup(hf),dedup(mf)
    result["critical"]=len(cf); result["high"]=len(hf); result["medium"]=len(mf)
    result["findings"]=[{**f,"severity":"CRITICAL"} for f in cf]+[{**f,"severity":"HIGH"} for f in hf]+[{**f,"severity":"MEDIUM"} for f in mf]
    if result["critical"]>0: result["risk_level"]="EXTREME"
    elif result["high"]>0: result["risk_level"]="HIGH"
    elif result["medium"]>0: result["risk_level"]="MEDIUM"
    else: result["risk_level"]="LOW"
    return result

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(SLUGS_FILE) as f: all_slugs = json.load(f)

    # Load source map and ordered slugs
    with open(SOURCE_MAP_FILE) as f: source_map = json.load(f)
    lightmake_set = set(source_map['lightmake'])
    
    # Resume from checkpoint
    checkpoint_file = os.path.join(OUTPUT_DIR, ".scan_checkpoint.json")
    existing_results = []
    done_set = set()
    start_time = time.time()
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file) as f: cp = json.load(f)
            existing_results = cp["results"]
            done_set = set(r["slug"] for r in existing_results)
            start_time = cp.get("start_time", time.time())
        except: pass

    # Build ordered work list: lightmake slugs first, then clawhub-only
    lightmake_queue = [s for s in all_slugs if s in lightmake_set and s not in done_set]
    clawhub_queue = [s for s in all_slugs if s not in lightmake_set and s not in done_set]
    
    print(f"=== ClawHub 全量安全扫描 v5 ===")
    print(f"已完成: {len(done_set):,}")
    print(f"Phase 1 (lightmake): {len(lightmake_queue):,}")
    print(f"Phase 2 (clawhub): {len(clawhub_queue):,}")
    print(f"开始: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results = existing_results
    done = 0; audited = 0; failed = 0; lm_hits = 0; ch_hits = 0

    # Phase 1: lightmake (fast, concurrent-safe)
    if lightmake_queue:
        print(f"▶ Phase 1: lightmake.site ({len(lightmake_queue):,} skills)...")
        for slug in lightmake_queue:
            meta = all_slugs.get(slug, {})
            try: result = audit_skill(slug, meta, use_clawhub=False)
            except Exception as e: result = {"slug":slug,"status":"error","error":str(e)[:100],"risk_level":"UNKNOWN","source":""}
            results.append(result)
            if result["status"]=="audited":
                audited += 1
                if result.get("source")=="lightmake": lm_hits += 1
            else: failed += 1
            done += 1
            if done % 500 == 0:
                elapsed = time.time()-start_time; rate = done/elapsed
                eta = (len(lightmake_queue)+len(clawhub_queue)-done)/rate/60
                print(f"  [{done:,}] ✅{audited:,} ❌{failed:,} lm:{lm_hits} | {rate:.0f}/s | ETA:{eta:.0f}m", flush=True)
            if done % 1000 == 0:
                with open(checkpoint_file,'w') as f: json.dump({"start_time":start_time,"results":results},f)
        print(f"  Phase 1 done: {lm_hits:,} audited, {failed:,} failed")

    # Phase 2: clawhub (rate limited)
    if clawhub_queue:
        print(f"\n▶ Phase 2: clawhub.ai ({len(clawhub_queue):,} skills, ~{len(clawhub_queue)/28:.0f}min)...")
        for slug in clawhub_queue:
            meta = all_slugs.get(slug, {})
            try: result = audit_skill(slug, meta, use_clawhub=True)
            except Exception as e: result = {"slug":slug,"status":"error","error":str(e)[:100],"risk_level":"UNKNOWN","source":""}
            results.append(result)
            if result["status"]=="audited":
                audited += 1
                if result.get("source")=="clawhub": ch_hits += 1
            else: failed += 1
            done += 1
            if done % 50 == 0:
                elapsed = time.time()-start_time; rate = done/elapsed
                remaining = len(clawhub_queue)-(done-len(lightmake_queue))
                eta = remaining/28 if remaining > 0 else 0
                print(f"  [{done-len(lightmake_queue):,}/{len(clawhub_queue):,}] ✅{audited:,} ❌{failed:,} ch:{ch_hits} | ETA:{eta:.0f}m", flush=True)
            if done % 200 == 0:
                with open(checkpoint_file,'w') as f: json.dump({"start_time":start_time,"results":results},f)
        print(f"  Phase 2 done: {ch_hits:,} audited")

    if os.path.exists(checkpoint_file): os.remove(checkpoint_file)

    elapsed = time.time()-start_time
    risk_counts = {}
    for r in results: risk_counts[r.get("risk_level","UNKNOWN")] = risk_counts.get(r.get("risk_level","UNKNOWN"),0)+1

    print(f"\n✅ 扫描完成！耗时: {elapsed/60:.1f}min ({elapsed/3600:.1f}h)")
    print(f"审计: {audited:,} (lightmake:{lm_hits} clawhub:{ch_hits}) | 失败: {failed:,}")
    print(f"风险:")
    _emoji = {"EXTREME":"⛔","HIGH":"🔴","MEDIUM":"🟡","LOW":"🟢","UNKNOWN":"❓"}
    for rl in ["EXTREME","HIGH","MEDIUM","LOW","UNKNOWN"]:
        c = risk_counts.get(rl,0)
        if c>0: print(f"  {_emoji[rl]} {rl}: {c:,}")

    ts = time.strftime('%Y%m%d_%H%M%S')
    jf = os.path.join(OUTPUT_DIR, f"skillhub-full-scan-{ts}.json")
    with open(jf,'w') as f: json.dump(results,f,ensure_ascii=False)
    print(f"JSON: {jf}")

    mf = jf.replace(".json",".md")
    order = {"EXTREME":0,"HIGH":1,"MEDIUM":2,"LOW":3,"UNKNOWN":4}
    results.sort(key=lambda r:(order.get(r["risk_level"],5),r["slug"]))
    with open(mf,'w') as f:
        f.write(f"# ClawHub 全量安全扫描报告\n\n**时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n**范围**: {len(results):,}\n\n**耗时**: {elapsed/60:.1f}min\n\n**成功**: {audited:,} (lm:{lm_hits} ch:{ch_hits}) | **失败**: {failed:,}\n\n## 风险\n\n| 等级 | 数量 |\n|------|------|\n")
        for rl in ["EXTREME","HIGH","MEDIUM","LOW","UNKNOWN"]:
            c=risk_counts.get(rl,0); e={"EXTREME":"⛔","HIGH":"🔴","MEDIUM":"🟡","LOW":"🟢","UNKNOWN":"❓"}[rl]
            f.write(f"| {e} {rl} | {c:,} |\n")
        f.write("\n---\n\n")
        ext=[r for r in results if r["risk_level"]=="EXTREME"]
        if ext:
            f.write(f"## ⛔ EXTREME ({len(ext):,})\n\n")
            for r in ext: f.write(f"- `{r['slug']}` dl:{r.get('downloads',0):,} ⭐{r.get('stars',0):,} src:{r.get('source','')} C:{r['critical']} H:{r['high']} M:{r['medium']}\n")
            f.write("\n")
        high=sorted([r for r in results if r["risk_level"]=="HIGH"],key=lambda r:r.get("downloads",0),reverse=True)
        if high:
            f.write(f"## 🔴 HIGH ({len(high):,})\n\n| 技能 | 下载 | 来源 | C|H|M |\n|------|------|------|-|-|-|\n")
            for r in high[:200]: f.write(f"| `{r['slug']}` | {r.get('downloads',0):,} | {r.get('source','')} | {r['critical']}|{r['high']}|{r['medium']} |\n")
            if len(high)>200: f.write(f"\n>+{len(high)-200:,} more\n\n")
        f.write(f"## 🟡 MEDIUM ({sum(1 for r in results if r['risk_level']=='MEDIUM'):,})\n\n## 🟢 LOW ({sum(1 for r in results if r['risk_level']=='LOW'):,})\n\n")
    print(f"Markdown: {mf}")

if __name__ == "__main__": main()
