/**
 * 採購爬蟲系統 — 前端互動邏輯
 */

// === Toast 通知 ===
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };

    toast.innerHTML = `<span>${icons[type] || icons.info}</span><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// === 手動推送到 Discord ===
async function pushToDiscord(tenderId, btnElement) {
    if (btnElement.disabled) return;

    const originalHtml = btnElement.innerHTML;
    btnElement.disabled = true;
    btnElement.innerHTML = '⏳ 推送中';

    try {
        const resp = await fetch(`/api/tenders/${tenderId}/push-discord`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await resp.json();

        if (data.success) {
            showToast(data.message || '已推送到 Discord', 'success');
            btnElement.innerHTML = '✓ 已推送';
            setTimeout(() => {
                btnElement.innerHTML = originalHtml;
                btnElement.disabled = false;
            }, 2000);
        } else {
            showToast(data.message || '推送失敗', 'error');
            btnElement.innerHTML = originalHtml;
            btnElement.disabled = false;
        }
    } catch (e) {
        showToast('網路錯誤', 'error');
        btnElement.innerHTML = originalHtml;
        btnElement.disabled = false;
    }
}

// === 追蹤/取消追蹤 ===
async function toggleTrack(tenderId, btnElement) {
    try {
        const resp = await fetch(`/api/tenders/${tenderId}/track`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await resp.json();

        if (data.success) {
            const isTracked = data.is_tracked;

            // 更新按鈕
            btnElement.classList.toggle('tracked', isTracked);
            btnElement.textContent = isTracked ? '★' : '☆';
            btnElement.title = isTracked ? '取消追蹤' : '加入追蹤';

            // 觸發動畫
            if (isTracked) {
                btnElement.style.animation = 'none';
                btnElement.offsetHeight; // force reflow
                btnElement.style.animation = 'star-pop 0.3s ease';
            }

            showToast(
                isTracked ? '已加入追蹤' : '已取消追蹤',
                isTracked ? 'success' : 'info'
            );

            // 更新統計數字
            updateStats();

            // 如果在追蹤頁面且取消追蹤，淡出卡片
            if (!isTracked) {
                const card = btnElement.closest('.tracked-card');
                if (card) {
                    card.style.transition = 'all 0.3s ease';
                    card.style.opacity = '0';
                    card.style.transform = 'translateX(30px)';
                    setTimeout(() => card.remove(), 300);
                }
            }
        } else {
            showToast('操作失敗', 'error');
        }
    } catch (e) {
        showToast('網路錯誤', 'error');
    }
}

// === 手動執行爬蟲 ===
async function manualScrape() {
    const btn = document.getElementById('btnManualScrape');
    if (btn.disabled) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span><span>執行中...</span>';
    btn.style.animation = 'none';

    try {
        const resp = await fetch('/api/scrape/run', { method: 'POST' });
        const data = await resp.json();

        if (data.started) {
            showToast(data.message, 'success');
            // 定期檢查狀態
            checkScrapeStatus('appeal');
        } else {
            showToast(data.message, 'warning');
            resetScrapeButton();
        }
    } catch (e) {
        showToast('請求失敗', 'error');
        resetScrapeButton();
    }
}

function resetScrapeButton() {
    const btn = document.getElementById('btnManualScrape');
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🚀</span><span>手動徵求爬蟲</span>';
        btn.style.animation = '';
    }
}

function resetBiddingScrapeButton() {
    const btn = document.getElementById('btnManualBiddingScrape');
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">📢</span><span>手動招標爬蟲</span>';
        btn.style.animation = '';
    }
}

async function manualBiddingScrape() {
    const btn = document.getElementById('btnManualBiddingScrape');
    if (!btn || btn.disabled) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span><span>執行中...</span>';

    try {
        const resp = await fetch('/api/scrape/run-bidding', { method: 'POST' });
        const data = await resp.json();
        if (data.started) {
            showToast(data.message, 'success');
            checkScrapeStatus('bidding');
        } else {
            showToast(data.message, 'warning');
            resetBiddingScrapeButton();
        }
    } catch (e) {
        showToast('請求失敗', 'error');
        resetBiddingScrapeButton();
    }
}

function resetJob104Button() {
    const btn = document.getElementById('btnManualJob104');
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🎯</span><span>手動 104 探測</span>';
        btn.style.animation = '';
    }
}

async function manualJob104() {
    const btn = document.getElementById('btnManualJob104');
    if (!btn || btn.disabled) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span><span>執行中...</span>';

    try {
        const resp = await fetch('/api/job104/manual', { method: 'POST' });
        const data = await resp.json();
        if (data.started) {
            showToast(data.message, 'success');
            checkScrapeStatus('job104');
        } else {
            showToast(data.message, 'warning');
            resetJob104Button();
        }
    } catch (e) {
        showToast('請求失敗', 'error');
        resetJob104Button();
    }
}

// === 爬蟲狀態檢查 ===
let statusCheckInterval = null;
let statusCheckCount = 0;

function setScrapeButtonRunning() {
    const btn = document.getElementById('btnManualScrape');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span><span>執行中...</span>';
    btn.style.animation = 'none';
}

function setBiddingScrapeButtonRunning() {
    const btn = document.getElementById('btnManualBiddingScrape');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span><span>執行中...</span>';
}

function setJob104ButtonRunning() {
    const btn = document.getElementById('btnManualJob104');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span><span>執行中...</span>';
}

/** 頁面載入或切換回來時，與後端執行狀態同步 */
async function syncScrapeButtonState() {
    try {
        const resp = await fetch('/api/scrape/status');
        const data = await resp.json();
        if (!data.is_running) return;
        if (data.mode === 'bidding') {
            setBiddingScrapeButtonRunning();
            checkScrapeStatus('bidding');
        } else if (data.mode === 'appeal') {
            setScrapeButtonRunning();
            checkScrapeStatus('appeal');
        } else if (data.mode === 'job104') {
            setJob104ButtonRunning();
            checkScrapeStatus('job104');
        } else {
            setScrapeButtonRunning();
            setBiddingScrapeButtonRunning();
            setJob104ButtonRunning();
            checkScrapeStatus('any');
        }
    } catch (e) {
        // ignore
    }
}

function checkScrapeStatus(kind) {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
    }
    statusCheckCount = 0;
    statusCheckInterval = setInterval(async () => {
        statusCheckCount++;
        try {
            const resp = await fetch('/api/scrape/status');
            const data = await resp.json();

            if (!data.is_running) {
                clearInterval(statusCheckInterval);
                statusCheckInterval = null;
                resetScrapeButton();
                resetBiddingScrapeButton();
                resetJob104Button();
                let label = '系統';
                if (kind === 'bidding') label = '公開招標爬蟲';
                else if (kind === 'appeal') label = '公開徵求爬蟲';
                else if (kind === 'job104') label = '104 探測器';
                showToast(`${label}執行完畢！`, 'success');
                setTimeout(() => location.reload(), 1500);
            }
        } catch (e) {
            // ignore
        }

        if (statusCheckCount >= 60) {
            clearInterval(statusCheckInterval);
            statusCheckInterval = null;
            resetScrapeButton();
            resetBiddingScrapeButton();
            resetJob104Button();
        }
    }, 5000);
}

// === 更新統計 ===
async function updateStats() {
    try {
        const resp = await fetch('/api/stats');
        const data = await resp.json();

        const el = (id) => document.getElementById(id);
        if (el('statTotal')) el('statTotal').textContent = data.total;
        if (el('statToday')) el('statToday').textContent = data.today;
        if (el('statTracked')) el('statTracked').textContent = data.tracked;
    } catch (e) {
        // ignore
    }
}

// === 排程資訊更新 ===
async function updateScheduleInfo() {
    try {
        const resp = await fetch('/api/schedule/info');
        const data = await resp.json();

        const nextTime = document.getElementById('nextScrapeTime');
        if (nextTime && data.next_scrape) {
            nextTime.textContent = data.next_scrape;
        }
    } catch (e) {
        // ignore
    }
}

// === Top Navbar 下拉選單與 Mobile Drawer ===
function toggleDropdown(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    const parent = document.getElementById('dropdownParent');
    if (parent) {
        parent.classList.toggle('open');
    }
}

function toggleMobileMenu(e) {
    if (e) e.stopPropagation();
    const drawer = document.getElementById('mobileDrawer');
    if (drawer) {
        drawer.classList.toggle('open');
    }
}

function toggleMobileSubmenu(e) {
    if (e) e.stopPropagation();
    const submenu = document.getElementById('mobileSubmenu');
    if (submenu) {
        submenu.classList.toggle('open');
    }
}

function initNavbar() {
    document.addEventListener('click', (e) => {
        const dropdownParent = document.getElementById('dropdownParent');
        if (dropdownParent && dropdownParent.classList.contains('open')) {
            if (!dropdownParent.contains(e.target)) {
                dropdownParent.classList.remove('open');
            }
        }
    });
}

// === 初始化 ===
document.addEventListener('DOMContentLoaded', () => {
    initNavbar();
    updateScheduleInfo();
    syncScrapeButtonState();

    setInterval(updateScheduleInfo, 60000);
});
