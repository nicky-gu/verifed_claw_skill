#!/usr/bin/env bash
# Skillhub 全量安全审计一键执行
# 用法: bash run_audit.sh [--scan-only] [--push-only] [--generate-only]
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
REPORT_DIR="${HOME}/.openclaw/reports"
SITE_DIR="${SITE_DIR:-/tmp/verifed_claw_skill}"
SITE_DATA_DIR="${SITE_DIR}/data"
SLUGS_FILE="${SLUGS_FILE:-/tmp/skillhub_complete_slugs.json}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PAT="${GITHUB_PAGES_PAT:-}"
SCAN_START_TIME=""

mkdir -p "$REPORT_DIR" "$SITE_DATA_DIR"

# 确保 git 已配置（新环境 clone 后可能没有）
if ! git config user.name >/dev/null 2>&1; then
    git config --global user.name "Skillhub Audit Bot"
    git config --global user.email "audit@skillhub.local"
fi

echo "=== Skillhub 全量安全审计 ==="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "站点目录: $SITE_DIR"
echo "报告目录: $REPORT_DIR"
echo ""

# Phase 1: 发现全部技能
if [[ "${1:-}" != "--push-only" && "${1:-}" != "--generate-only" ]]; then
    echo "📥 阶段1: 发现全部技能..."
    SCAN_START_TIME=$(date +%s)
    python3 -u "$SKILL_DIR/scripts/discover_slugs.py" --output "$SLUGS_FILE"
    slug_count=$(python3 -c "import json; print(len(json.load(open('$SLUGS_FILE'))))")
    echo "  发现 $slug_count 个技能"

    # Phase 2: 全量扫描
    echo ""
    echo "🔍 阶段2: 全量安全扫描..."
    SLUGS_FILE="$SLUGS_FILE" python3 -u "$SKILL_DIR/scripts/skillhub_full_scan.py"
    echo ""

    # 找到最新的扫描结果
    LATEST=$(ls -t "$REPORT_DIR"/skillhub-full-scan-*.json 2>/dev/null | head -1)
    if [[ -z "$LATEST" ]]; then
        echo "  ❌ 未找到扫描结果"
        exit 1
    fi
    echo "📄 扫描结果: $LATEST"
fi

# Phase 3: 生成分片数据
if [[ "${1:-}" != "--push-only" ]]; then
    echo ""
    echo "📦 阶段3: 生成分片站点数据..."
    LATEST=$(ls -t "$REPORT_DIR"/skillhub-full-scan-*.json 2>/dev/null | head -1)
    if [[ -z "$LATEST" ]]; then
        echo "  ❌ 未找到扫描结果，请先运行扫描"
        exit 1
    fi

    # 计算扫描耗时
    if [[ -n "${SCAN_START_TIME:-}" ]]; then
        SCAN_END_TIME=$(date +%s)
        SCAN_ELAPSED=$(( SCAN_END_TIME - SCAN_START_TIME ))
        SCAN_DURATION=$(printf "%d分%02d秒" $((SCAN_ELAPSED/60)) $((SCAN_ELAPSED%60)))
    else
        SCAN_DURATION="N/A"
    fi

    SCAN_DURATION="$SCAN_DURATION" python3 -u "$SKILL_DIR/scripts/generate_site_data.py" "$LATEST" "$SITE_DATA_DIR"
fi

# Phase 4: 更新站点并推送
echo ""
echo "🚀 阶段4: 更新 GitHub Pages..."

# 更新扫描时间 meta 标签
SCAN_DATE=$(date '+%Y年%-m月%-d日 %H:%M CST')
if [[ -f "$SITE_DIR/index.html" ]]; then
    sed -i "s|content=\"[^\"]*\" data-scan-date|content=\"$SCAN_DATE\" data-scan-date|" "$SITE_DIR/index.html"
    # 从 summary 读取 scan_duration 写入 meta
    if [[ -f "$SITE_DATA_DIR/audit-summary.json" ]]; then
        DURATION_FROM_SUMMARY=$(python3 -c "
import json
with open('$SITE_DATA_DIR/audit-summary.json') as f:
    s = json.load(f)
print(s.get('scan_duration', '') or '')
" 2>/dev/null)
        if [[ -n "$DURATION_FROM_SUMMARY" ]]; then
            sed -i "s|content=\"[^\"]*\" data-scan-duration|content=\"$DURATION_FROM_SUMMARY\" data-scan-duration|" "$SITE_DIR/index.html"
        fi
    fi
fi

# 统计（在 if 外面赋值，确保变量可见）
COMMIT_MSG="Scan $(date '+%Y-%m-%d')"
if [[ -f "$SITE_DATA_DIR/audit-summary.json" ]]; then
    COMMIT_MSG=$(python3 -c "
import json
with open('$SITE_DATA_DIR/audit-summary.json') as f:
    s = json.load(f)
rc = s['risk_counts']
print(f\"Scan $(date '+%Y-%m-%d'): E:{rc.get('EXTREME',0)} H:{rc.get('HIGH',0)} M:{rc.get('MEDIUM',0)} L:{rc.get('LOW',0)} U:{rc.get('UNKNOWN',0)} Total:{s['total']}\")
")
    echo "  统计: $COMMIT_MSG"
fi

cd "$SITE_DIR"

git add -A
git commit -m "$COMMIT_MSG" --allow-empty 2>/dev/null || true

if [[ -z "$PAT" ]]; then
    echo "  ⚠️ GITHUB_PAGES_PAT 未设置，跳过推送"
    echo "  设置方式: export GITHUB_PAGES_PAT=ghp_xxxx"
    echo "  或手动推送: python3 scripts/push_github_api.py $SITE_DIR"
    exit 0
fi

# 推送（通过 GitHub API，绕过 github.com TLS 阻断）
python3 scripts/push_github_api.py "$SITE_DIR" 2>&1 || {
    echo "  ❌ Push 失败，可能需要重试"
    echo "  手动: python3 scripts/push_github_api.py $SITE_DIR"
    exit 1
}

echo ""
echo "✅ 全部完成！"
echo "   📊 站点: http://pages.789123123.xyz/verifed_claw_skill/"
echo "   📅 扫描时间: $SCAN_DATE"
