// Skillhub Audit - Chunked Loading + Per-Skill Details
const RISK_ORDER = { EXTREME: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };
const RISK_EMOJI = { EXTREME: '⛔', HIGH: '🔴', MEDIUM: '🟡', LOW: '🟢', UNKNOWN: '❓' };
const RISK_LABELS = { EXTREME: '建议禁止安装', HIGH: '需安全审批', MEDIUM: '需谨慎安装', LOW: '可安全安装', UNKNOWN: '未知' };

let allData = [];
let summary = null;
let detailCache = {};
let currentFilter = 'all';
let currentSearch = '';
let currentSort = 'risk';

function formatBytes(bytes) {
    if (!bytes) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

// ===== Data Loading =====

async function loadSummary() {
    const resp = await fetch('data/audit-summary.json');
    summary = await resp.json();
}

async function loadAllChunks() {
    if (!summary) return;
    const results = await Promise.all(
        summary.files.map(f =>
            fetch(`data/${f}`).then(r => r.json()).catch(() => [])
        )
    );
    allData = results.flat();
}

async function loadDetail(slug) {
    if (detailCache[slug]) return detailCache[slug];
    try {
        const resp = await fetch(`data/details/${slug}.json`);
        if (!resp.ok) return null;
        const detail = await resp.json();
        detailCache[slug] = detail;
        return detail;
    } catch (e) {
        return null;
    }
}

// ===== UI Updates =====

function updateRunDetails() {
    if (!summary) return;
    const s = summary;
    document.getElementById('run-total').textContent = s.total.toLocaleString();
    document.getElementById('run-success').textContent = s.audited.toLocaleString();
    document.getElementById('run-failed').textContent = s.failed.toLocaleString();
    document.getElementById('run-files').textContent = s.total_files.toLocaleString();
    document.getElementById('run-size').textContent = formatBytes(s.total_size);
    document.getElementById('run-scripts').textContent = s.has_scripts.toLocaleString();
    document.getElementById('run-hooks').textContent = s.has_hooks.toLocaleString();
    document.getElementById('run-duration').textContent = s.scan_duration;

    const sp = (s.audited / s.total * 100).toFixed(1);
    const fp = (s.failed / s.total * 100).toFixed(1);
    document.getElementById('progress-success').style.width = sp + '%';
    document.getElementById('progress-fail').style.width = fp + '%';
    document.getElementById('progress-success-label').textContent = `✅ 成功 ${s.audited.toLocaleString()} (${sp}%)`;
    document.getElementById('progress-fail-label').textContent = `❌ 失败 ${s.failed.toLocaleString()} (${fp}%)`;
    document.getElementById('scan-date').textContent = s.scan_date;
    document.getElementById('scan-duration').textContent = s.scan_duration;
}

function updateStatsFromSummary() {
    if (!summary) return;
    const rc = summary.risk_counts;
    document.getElementById('count-extreme').textContent = (rc.EXTREME || 0).toLocaleString();
    document.getElementById('count-high').textContent = (rc.HIGH || 0).toLocaleString();
    document.getElementById('count-medium').textContent = (rc.MEDIUM || 0).toLocaleString();
    document.getElementById('count-low').textContent = (rc.LOW || 0).toLocaleString();
    document.getElementById('count-total').textContent = summary.total.toLocaleString();
}

// ===== Table =====

function getFilteredData() {
    let data = allData;
    if (currentFilter !== 'all') {
        data = data.filter(d => d.r === currentFilter);
    }
    if (currentSearch) {
        const q = currentSearch.toLowerCase();
        data = data.filter(d => d.s.toLowerCase().includes(q));
    }
    data = [...data].sort((a, b) => {
        switch (currentSort) {
            case 'risk': return (RISK_ORDER[a.r] || 9) - (RISK_ORDER[b.r] || 9) || a.s.localeCompare(b.s);
            case 'slug': return a.s.localeCompare(b.s);
            case 'critical': return (b.c || 0) - (a.c || 0);
            case 'high': return (b.h || 0) - (a.h || 0);
            case 'files': return (b.f || 0) - (a.f || 0);
            default: return 0;
        }
    });
    return data;
}

function renderTable() {
    const data = getFilteredData();
    const tbody = document.getElementById('results-body');
    if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="loading">没有找到匹配结果</td></tr>';
        return;
    }
    const show = data.slice(0, 500);
    const total = data.length;

    tbody.innerHTML = show.map(d => {
        const cls = `risk-${d.r.toLowerCase()}`;
        const emoji = RISK_EMOJI[d.r] || '❓';
        const scripts = d.S ? '<span class="feature-tag">scripts</span>' : '';
        return `<tr>
            <td><span class="risk-badge ${cls}">${emoji} ${d.r}</span></td>
            <td class="slug-cell" data-slug="${d.s}">${d.s}</td>
            <td>${d.f || 0}</td>
            <td>${formatBytes(d.z)}</td>
            <td>${d.c || 0}</td>
            <td>${d.h || 0}</td>
            <td>${d.m || 0}</td>
            <td>${scripts}</td>
            <td>✅</td>
        </tr>`;
    }).join('');

    if (total > 500) {
        tbody.innerHTML += `<tr><td colspan="9" style="text-align:center;color:var(--text-secondary);padding:12px;">显示前 500 条，共 ${total.toLocaleString()} 条</td></tr>`;
    }
}

// ===== Detail Panel =====

async function showDetail(slug) {
    const item = allData.find(x => x.s === slug);
    if (!item) return;

    const panel = document.getElementById('detail-panel');
    panel.classList.remove('hidden');
    document.getElementById('detail-slug').textContent = slug;

    const cls = `risk-${item.r.toLowerCase()}`;
    const emoji = RISK_EMOJI[item.r] || '❓';
    document.getElementById('detail-risk-badge').innerHTML = `<span class="risk-badge ${cls}">${emoji} ${item.r} — ${RISK_LABELS[item.r] || ''}</span>`;

    // Basic info immediately
    let html = `
        <div class="detail-meta">
            <div class="meta-row"><span class="meta-label">文件数</span><span>${item.f || 0}</span></div>
            <div class="meta-row"><span class="meta-label">总大小</span><span>${formatBytes(item.z)}</span></div>
            <div class="meta-row"><span class="meta-label">状态</span><span>${item.st === 'audited' ? '✅ 已审计' : '❌ ' + item.st}</span></div>
            <div class="meta-row"><span class="meta-label">可执行脚本</span><span>${item.S ? '⚠️ 是' : '否'}</span></div>
        </div>
    `;

    // Show counts
    if (item.c > 0 || item.h > 0 || item.m > 0) {
        html += `<div class="detail-counts">`;
        if (item.c) html += `<span class="count-critical">⛔ CRITICAL ×${item.c}</span>`;
        if (item.h) html += `<span class="count-high">🔴 HIGH ×${item.h}</span>`;
        if (item.m) html += `<span class="count-medium">🟡 MEDIUM ×${item.m}</span>`;
        html += `</div>`;
    }

    // Load detail if available (EXTREME skills)
    if (item.r === 'EXTREME') {
        html += '<div id="detail-findings" class="loading">⏳ 加载详细扫描结果...</div>';
        document.getElementById('detail-content').innerHTML = html;

        const detail = await loadDetail(slug);
        const findingsDiv = document.getElementById('detail-findings');
        if (!detail) {
            findingsDiv.innerHTML = '<p style="color:var(--text-secondary)">详细数据加载失败</p>';
            return;
        }

        let detailHtml = '';

        // Extra meta from detail
        if (detail.name) detailHtml += `<div class="detail-name">📌 ${detail.name}</div>`;
        if (detail.version) detailHtml += `<div class="detail-version">版本: ${detail.version}</div>`;
        if (detail.has_hooks) detailHtml += `<div class="detail-warn">⚠️ 包含 Hooks</div>`;
        if (detail.has_exec_directives) detailHtml += `<div class="detail-warn">⚠️ 包含 exec 指令</div>`;

        // Findings
        if (detail.findings && detail.findings.length > 0) {
            // Group by severity
            const groups = { CRITICAL: [], HIGH: [], MEDIUM: [] };
            detail.findings.forEach(f => {
                const sev = (f.sev || 'MEDIUM').toUpperCase();
                if (groups[sev]) groups[sev].push(f);
                else groups.MEDIUM.push(f);
            });

            for (const [sev, items] of Object.entries(groups)) {
                if (!items.length) continue;
                const sevEmoji = sev === 'CRITICAL' ? '⛔' : sev === 'HIGH' ? '🔴' : '🟡';
                const sevClass = sev === 'CRITICAL' ? 'critical' : sev === 'HIGH' ? 'high' : 'medium';
                detailHtml += `<div class="findings-group">
                    <h4 class="findings-title findings-title-${sevClass}">${sevEmoji} ${sev} (${items.length})</h4>`;
                items.forEach(f => {
                    detailHtml += `<div class="finding-item finding-${sevClass}">
                        <div class="finding-rule">📋 ${f.rule || 'unknown'}</div>
                        <div class="finding-context">${escapeHtml(f.ctx || '')}</div>
                    </div>`;
                });
                detailHtml += `</div>`;
            }
        } else {
            detailHtml += '<p style="color:var(--text-secondary);margin-top:12px;">无详细扫描结果</p>';
        }

        findingsDiv.innerHTML = detailHtml;
        findingsDiv.classList.remove('loading');
    } else {
        html += '<p style="color:var(--text-secondary);margin-top:12px;">💡 详细扫描结果仅对 EXTREME 级别技能提供。如需查看此技能的完整扫描信息，请运行本地安全扫描。</p>';
        document.getElementById('detail-content').innerHTML = html;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ===== Events =====

document.getElementById('search-input').addEventListener('input', e => {
    currentSearch = e.target.value;
    renderTable();
});

document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.dataset.filter;
        renderTable();
    });
});

document.getElementById('sort-select').addEventListener('change', e => {
    currentSort = e.target.value;
    renderTable();
});

document.getElementById('detail-close').addEventListener('click', () => {
    document.getElementById('detail-panel').classList.add('hidden');
});

document.addEventListener('click', e => {
    const slugCell = e.target.closest('.slug-cell');
    if (slugCell) showDetail(slugCell.dataset.slug);
});

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') document.getElementById('detail-panel').classList.add('hidden');
});

// ===== Init =====
(async () => {
    try {
        await loadSummary();
        updateRunDetails();
        updateStatsFromSummary();
        document.getElementById('results-body').innerHTML = '<tr><td colspan="9" class="loading">⏳ 正在加载审计数据...</td></tr>';
        await loadAllChunks();
        renderTable();
    } catch (e) {
        document.getElementById('results-body').innerHTML = '<tr><td colspan="9" class="loading">❌ 加载失败: ' + e.message + '</td></tr>';
    }
})();
