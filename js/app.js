// Skillhub Audit - Main Application (Chunked Loading)
const RISK_ORDER = { EXTREME: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };
const RISK_EMOJI = { EXTREME: '⛔', HIGH: '🔴', MEDIUM: '🟡', LOW: '🟢', UNKNOWN: '❓' };

let allData = [];
let summary = null;
let currentFilter = 'all';
let currentSearch = '';
let currentSort = 'risk';

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

// Load summary first (tiny ~0.5KB)
async function loadSummary() {
    try {
        const resp = await fetch('data/audit-summary.json');
        summary = await resp.json();
        updateRunDetails();
        updateStatsFromSummary();
    } catch (e) {
        console.error('Failed to load summary:', e);
    }
}

// Update run details panel
function updateRunDetails() {
    if (!summary) return;
    document.getElementById('run-total').textContent = summary.total.toLocaleString();
    document.getElementById('run-success').textContent = summary.audited.toLocaleString();
    document.getElementById('run-failed').textContent = summary.failed.toLocaleString();
    document.getElementById('run-files').textContent = summary.total_files.toLocaleString();
    document.getElementById('run-size').textContent = formatBytes(summary.total_size);
    document.getElementById('run-scripts').textContent = summary.has_scripts.toLocaleString();
    document.getElementById('run-hooks').textContent = summary.has_hooks.toLocaleString();
    document.getElementById('run-duration').textContent = summary.scan_duration;

    const successPct = (summary.audited / summary.total * 100).toFixed(1);
    const failPct = (summary.failed / summary.total * 100).toFixed(1);
    document.getElementById('progress-success').style.width = successPct + '%';
    document.getElementById('progress-fail').style.width = failPct + '%';
    document.getElementById('progress-success-label').textContent = `✅ 成功 ${summary.audited.toLocaleString()} (${successPct}%)`;
    document.getElementById('progress-fail-label').textContent = `❌ 失败 ${summary.failed.toLocaleString()} (${failPct}%)`;

    document.getElementById('scan-date').textContent = summary.scan_date;
    document.getElementById('scan-duration').textContent = summary.scan_duration;
}

// Quick stats from summary (no full load needed)
function updateStatsFromSummary() {
    if (!summary) return;
    document.getElementById('count-extreme').textContent = (summary.risk_counts.EXTREME || 0);
    document.getElementById('count-high').textContent = (summary.risk_counts.HIGH || 0);
    document.getElementById('count-medium').textContent = (summary.risk_counts.MEDIUM || 0);
    document.getElementById('count-low').textContent = (summary.risk_counts.LOW || 0);
    document.getElementById('count-total').textContent = summary.total;
}

// Load data chunks on demand based on filter
async function loadDataForFilter(filter) {
    const files = summary ? summary.files : [];
    let dataFiles = [];

    if (filter === 'all') {
        dataFiles = files;
    } else {
        dataFiles = files.filter(f => f.includes(filter.toLowerCase()));
    }

    // Load all matching chunks
    const chunks = await Promise.all(
        dataFiles.map(f => fetch(`data/${f}`).then(r => r.json()).catch(e => { console.error(e); return []; }))
    );
    return chunks.flat();
}

// Initial load: load summary + render table with "load more" for filtered views
async function loadData() {
    try {
        // Load summary first
        await loadSummary();

        // Pre-load EXTREME (small, most important) + show others on demand
        const extremeData = await loadDataForFilter('EXTREME');
        allData = extremeData;

        // Show loading indicator for remaining
        document.getElementById('results-body').innerHTML = '<tr><td colspan="9" class="loading">✅ 已加载 EXTREME 技能。切换筛选器以加载其他类别数据。</td></tr>';

        // Update stats with what we have
        renderTable();

        // Background: load all data for full search
        loadAllDataBackground();
    } catch (e) {
        document.getElementById('results-body').innerHTML = '<tr><td colspan="9" class="loading">❌ 加载失败: ' + e.message + '</td></tr>';
    }
}

async function loadAllDataBackground() {
    try {
        if (!summary) return;
        const allChunks = await Promise.all(
            summary.files.map(f => fetch(`data/${f}`).then(r => r.json()).catch(e => { console.error(e); return []; }))
        );
        allData = allChunks.flat();
        renderTable();
    } catch (e) {
        console.error('Background load failed:', e);
    }
}

// Filter & sort
function getFilteredData() {
    let data = [...allData];

    if (currentFilter !== 'all') {
        data = data.filter(d => d.risk_level === currentFilter);
    }

    if (currentSearch) {
        const q = currentSearch.toLowerCase();
        data = data.filter(d =>
            d.slug.toLowerCase().includes(q) ||
            (d.name || '').toLowerCase().includes(q)
        );
    }

    data.sort((a, b) => {
        switch (currentSort) {
            case 'risk': return (RISK_ORDER[a.risk_level] || 9) - (RISK_ORDER[b.risk_level] || 9) || a.slug.localeCompare(b.slug);
            case 'slug': return a.slug.localeCompare(b.slug);
            case 'critical': return (b.critical || 0) - (a.critical || 0);
            case 'high': return (b.high || 0) - (a.high || 0);
            case 'files': return (b.file_count || 0) - (a.file_count || 0);
            default: return 0;
        }
    });

    return data;
}

// Render table
function renderTable() {
    const data = getFilteredData();
    const tbody = document.getElementById('results-body');

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="loading">没有找到匹配结果</td></tr>';
        return;
    }

    const show = data.slice(0, 500);
    const total = data.length;

    tbody.innerHTML = show.map(d => {
        const riskClass = `risk-${d.risk_level.toLowerCase()}`;
        const emoji = RISK_EMOJI[d.risk_level] || '❓';
        const status = d.status === 'audited'
            ? '<span class="status-ok">✅</span>'
            : `<span class="status-fail" title="${d.error || ''}">❌</span>`;

        const features = [];
        if (d.has_scripts) features.push('<span class="feature-tag">scripts</span>');
        if (d.has_hooks) features.push('<span class="feature-tag">hooks</span>');
        if (d.has_exec_directives) features.push('<span class="feature-tag">exec</span>');

        return `<tr>
            <td><span class="risk-badge ${riskClass}">${emoji} ${d.risk_level}</span></td>
            <td class="slug-cell" data-slug="${d.slug}">${d.slug}</td>
            <td>${d.file_count || 0}</td>
            <td>${formatBytes(d.total_size || 0)}</td>
            <td>${d.critical || 0}</td>
            <td>${d.high || 0}</td>
            <td>${d.medium || 0}</td>
            <td>${features.join('')}</td>
            <td>${status}</td>
        </tr>`;
    }).join('');

    if (total > 500) {
        tbody.innerHTML += `<tr><td colspan="9" style="text-align:center;color:var(--text-secondary);padding:12px;">显示前 500 条，共 ${total.toLocaleString()} 条。请缩小搜索范围。</td></tr>`;
    }
}

// Show detail
function showDetail(slug) {
    const d = allData.find(x => x.slug === slug);
    if (!d) return;

    const panel = document.getElementById('detail-panel');
    panel.classList.remove('hidden');
    document.getElementById('detail-slug').textContent = d.slug;

    const riskClass = `risk-${d.risk_level.toLowerCase()}`;
    const emoji = RISK_EMOJI[d.risk_level] || '❓';
    document.getElementById('detail-risk-badge').innerHTML = `<span class="risk-badge ${riskClass}">${emoji} ${d.risk_level}</span>`;

    let html = `
        <p><strong>状态:</strong> ${d.status}</p>
        <p><strong>文件数:</strong> ${d.file_count} | <strong>大小:</strong> ${formatBytes(d.total_size)}</p>
        ${d.name ? `<p><strong>名称:</strong> ${d.name}</p>` : ''}
        ${d.version ? `<p><strong>版本:</strong> ${d.version}</p>` : ''}
    `;

    if (d.has_scripts) html += '<p>⚠️ <strong>包含可执行脚本</strong></p>';
    if (d.has_hooks) html += '<p>⚠️ <strong>包含 hooks</strong></p>';
    if (d.has_exec_directives) html += '<p>⚠️ <strong>含 exec 指令</strong></p>';

    if (d.findings && d.findings.length > 0) {
        html += '<h3 style="margin:16px 0 8px">🔍 安全发现</h3>';
        d.findings.forEach(f => {
            html += `<div class="finding-item finding-${f.severity.toLowerCase()}">
                <div class="finding-rule">[${f.severity}] ${f.rule_id || f.pattern || ''}</div>
                <div class="finding-context">${f.context || f.severity}</div>
            </div>`;
        });
    }

    if (d.error) {
        html += `<p style="margin-top:16px;color:var(--extreme)">❌ 错误: ${d.error}</p>`;
    }

    document.getElementById('detail-content').innerHTML = html;
}

// Event listeners
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

// Init
loadData();
