#!/usr/bin/env python3
"""
生成 GitHub Pages 站点数据（分片方案）
从全量扫描结果生成:
  1. audit-summary.json — 统计摘要（~0.5KB）
  2. audit-N.json — 列表分片（~26KB/个，350条/chunk）
  3. details/{slug}.json — EXTREME 技能独立详情（按需加载）
  4. details/findings-{N}.json — HIGH/MEDIUM/LOW/UNIQUE findings 批次（按需加载）
"""
import json, os, sys, time

def generate_site_data(scan_json_path, site_data_dir):
    with open(scan_json_path) as f:
        data = json.load(f)

    details_dir = os.path.join(site_data_dir, "details")
    os.makedirs(details_dir, exist_ok=True)

    # 清理旧数据文件
    for f in os.listdir(site_data_dir):
        if f.startswith("audit-"):
            os.remove(os.path.join(site_data_dir, f))
    if os.path.exists(details_dir):
        for f in os.listdir(details_dir):
            if f.endswith(".json"):
                os.remove(os.path.join(details_dir, f))

    print(f"=== 生成站点数据 ===")
    print(f"总技能数: {len(data)}")

    # 1. 超紧凑列表分片（所有技能）
    all_slim = []
    for d in data:
        all_slim.append({
            "s": d["slug"],
            "r": d.get("risk_level", "UNKNOWN"),
            "f": d["file_count"] or 0,
            "z": d["total_size"] or 0,
            "S": 1 if d.get("has_scripts") else 0,
            "c": d.get("critical") or 0,
            "h": d.get("high") or 0,
            "m": d.get("medium") or 0,
        })

    CHUNK = 350
    files_list = []
    for i in range(0, len(all_slim), CHUNK):
        chunk = all_slim[i:i+CHUNK]
        fn = f"audit-{i//CHUNK + 1}.json"
        out = json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))
        with open(os.path.join(site_data_dir, fn), "w") as f:
            f.write(out)
        files_list.append(fn)
    print(f"列表分片: {len(files_list)} 个文件")

    # 2. EXTREME 技能独立详情（含完整 findings + context）
    detail_count = 0
    for d in data:
        if d.get("risk_level") != "EXTREME":
            continue
        slug = d["slug"]
        findings = []
        for fi in (d.get("findings") or []):
            findings.append({
                "sev": fi.get("severity", ""),
                "rule": fi.get("rule_id", ""),
                "ctx": (fi.get("context") or "")[:150]
            })
        entry = {
            "slug": slug,
            "name": (d.get("name") or "")[:80],
            "version": d.get("version", ""),
            "risk_level": "EXTREME",
            "file_count": d["file_count"] or 0,
            "total_size": d["total_size"] or 0,
            "has_scripts": d.get("has_scripts", False),
            "has_hooks": d.get("has_hooks", False),
            "has_exec_directives": d.get("has_exec_directives", False),
            "status": d["status"],
            "critical": d.get("critical") or 0,
            "high": d.get("high") or 0,
            "medium": d.get("medium") or 0,
            "findings": findings
        }
        fn = os.path.join(details_dir, f"{slug}.json")
        out = json.dumps(entry, ensure_ascii=False, separators=(',', ':'))
        with open(fn, "w") as f:
            f.write(out)
        detail_count += 1
    print(f"EXTREME 详情: {detail_count} 个文件")

    # 3. HIGH/MEDIUM/LOW/UNKNOWN findings 批次文件（unique rule IDs）
    non_extreme = []
    for d in data:
        if d.get("risk_level") == "EXTREME":
            continue
        rules = list(set(
            fi.get("rule_id", "")
            for fi in (d.get("findings") or [])
            if fi.get("severity") in ("HIGH", "CRITICAL")
        ))
        non_extreme.append({
            "s": d["slug"],
            "n": (d.get("name") or "")[:40],
            "f": d["file_count"] or 0,
            "z": d["total_size"] or 0,
            "S": 1 if d.get("has_scripts") else 0,
            "H": 1 if d.get("has_hooks") else 0,
            "E": 1 if d.get("has_exec_directives") else 0,
            "c": d.get("critical") or 0,
            "h": d.get("high") or 0,
            "m": d.get("medium") or 0,
            "st": d["status"],
            "r": rules,
        })

    findings_files = []
    FINDINGS_CHUNK = 350
    for i in range(0, len(non_extreme), FINDINGS_CHUNK):
        chunk = non_extreme[i:i+FINDINGS_CHUNK]
        fn = f"findings-{i//FINDINGS_CHUNK + 1}.json"
        fp = os.path.join(details_dir, fn)
        out = json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))
        with open(fp, "w") as f:
            f.write(out)
        findings_files.append(fn)

    print(f"Findings 批次: {len(findings_files)} 个文件")

    # 4. Summary
    risk_counts = {}
    total_files = 0
    total_size = 0
    audited = 0
    failed = 0
    has_scripts = 0
    has_hooks = 0
    for d in data:
        rl = d.get("risk_level", "UNKNOWN")
        risk_counts[rl] = risk_counts.get(rl, 0) + 1
        if d["status"] == "audited":
            audited += 1
        else:
            failed += 1
        total_files += d.get("file_count") or 0
        total_size += d.get("total_size") or 0
        if d.get("has_scripts"):
            has_scripts += 1
        if d.get("has_hooks"):
            has_hooks += 1

    scan_duration = os.environ.get("SCAN_DURATION", None)
    summary = {
        "scan_date": time.strftime("%Y-%m-%d %H:%M CST"),
        "scan_duration": scan_duration,
        "total": len(data),
        "audited": audited,
        "failed": failed,
        "total_files": total_files,
        "total_size": total_size,
        "has_scripts": has_scripts,
        "has_hooks": has_hooks,
        "risk_counts": risk_counts,
        "files": files_list,
        "detail_count": detail_count,
        "findings_files": findings_files,
    }
    with open(os.path.join(site_data_dir, "audit-summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, separators=(',', ':'))

    print(f"\n统计:")
    for rl in ["EXTREME", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]:
        c = risk_counts.get(rl, 0)
        if c > 0:
            print(f"  {rl}: {c}")
    print(f"  审计成功: {audited}, 失败: {failed}")
    print(f"\n✅ 生成完成")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 generate_site_data.py <scan_json_path> <site_data_dir>")
        sys.exit(1)
    generate_site_data(sys.argv[1], sys.argv[2])
