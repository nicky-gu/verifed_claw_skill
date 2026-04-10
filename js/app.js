// Skillhub Audit - Main Application
const RISK_ORDER = { EXTREME: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };
const RISK_EMOJI = { EXTREME: '⛔', HIGH: '🔴', MEDIUM: '🟡', LOW: '🟢', UNKNOWN: '❓' };

let allData = [];
let currentFilter = 'all';
let currentSearch = '';
let currentSort = 'risk';

// Format bytes
function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

// Load data
async function loadData() {
    try {
        const resp = await fetch('data/audit-results.json');
        allData = await resp.json();
        updateStats();
        renderTable();
        document.getElementById('scan-date').textContent = document.querySelector('meta[data-scan-date]')?.content || new Date().toLocaleDateString('zh-CN');
        document.getElementById('scan-duration').textContent = document.querySelector('meta[data-scan-duration]')?.content || '-';
    } catch (e) {
        document.getElementById('results-body').innerHTML = '<tr><td colspan="9" class="loading">❌ 加载失败: ' + e.message + '</td></tr>';
    }
}

// Update stats
function updateStats() {
    const counts = { EXTREME: 0, HIGH: 0, MEDIUM: 0, LOW: 0, UNKNOWN: 0, total: allData.length };
    allData.forEach(d => { counts[d.risk_level] = (counts[d.risk_level] || 0) + 1; });
    document.getElementById('count-extreme').textContent = counts.EXTREME;
    document.getElementById('count-high').textContent = counts.HIGH;
    document.getElementById('count-medium').textContent = counts.MEDIUM;
    document.getElementById('count-low').textContent = counts.LOW;
    document.getElementById('count-total').textContent = counts.total;
}

// Filter & sort
function getFilteredData() {
    let data = [...allData];

    // Filter
    if (currentFilter !== 'all') {
        data = data.filter(d => d.risk_level === currentFilter);
    }

    // Search
    if (currentSearch) {
        const q = currentSearch.toLowerCase();
        data = data.filter(d =>
            d.slug.toLowerCase().includes(q) ||
            (d.name || '').toLowerCase().includes(q)
        );
    }

    // Sort
    data.sort((a, b) => {
        switch (currentSort) {
            case 'risk': return (RISK_ORDER[a.risk_level] || 9) - (RISK_ORDER[b.risk_level] || 9) || a.slug.localeCompare(b.slug);
            case 'slug': return a.slug.localeCompare(b.slug);
            case 'critical': return b.critical - a.critical;
            case 'high': return b.high - a.high;
            case 'files': return b.file_count - a.file_count;
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
        tbody.innerHTML = '<tr><td colspan="9" class="loading">No results found</td></tr>';
        return;
    }

    // Show max 500 rows for performance, with a note
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
        if (d.suspicious_files && d.suspicious_files.length) features.push('<span class="feature-tag">⚠️suspicious</span>');

        return `<tr>
            <td><span class="risk-badge ${riskClass}">${emoji} ${d.risk_level}</span></td>
            <td class="slug-cell" data-slug="${d.slug}">${d.slug}</td>
            <td>${d.file_count}</td>
            <td>${formatBytes(d.total_size)}</td>
            <td>${d.critical || 0}</td>
            <td>${d.high || 0}</td>
            <td>${d.medium || 0}</td>
            <td>${features.join('')}</td>
            <td>${status}</td>
        </tr>`;
    }).join('');

    if (total > 500) {
        tbody.innerHTML += `<tr><td colspan="9" style="text-align:center;color:var(--text-secondary);padding:12px;">显示前 500 条，共 ${total} 条。请缩小搜索范围。</td></tr>`;
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
