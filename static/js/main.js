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
            checkScrapeStatus();
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
        btn.innerHTML = '<span class="btn-icon">🚀</span><span>手動執行爬蟲</span>';
        btn.style.animation = '';
    }
}

// === 爬蟲狀態檢查 ===
let statusCheckCount = 0;
function checkScrapeStatus() {
    statusCheckCount = 0;
    const interval = setInterval(async () => {
        statusCheckCount++;
        try {
            const resp = await fetch('/api/scrape/status');
            const data = await resp.json();

            if (!data.is_running) {
                clearInterval(interval);
                resetScrapeButton();
                showToast('爬蟲執行完畢！', 'success');
                // 刷新頁面載入新資料
                setTimeout(() => location.reload(), 1500);
            }
        } catch (e) {
            // ignore
        }

        // 最多檢查 60 次（5 分鐘）
        if (statusCheckCount >= 60) {
            clearInterval(interval);
            resetScrapeButton();
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

// === Sidebar 切換（行動裝置）===
function initSidebar() {
    const mobileToggle = document.getElementById('mobileToggle');
    const sidebar = document.getElementById('sidebar');

    if (mobileToggle) {
        mobileToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });

        // 點擊主內容區關閉
        document.querySelector('.main-content').addEventListener('click', () => {
            sidebar.classList.remove('open');
        });
    }
}

// === 初始化 ===
document.addEventListener('DOMContentLoaded', () => {
    initSidebar();
    updateScheduleInfo();

    // 定期更新排程資訊
    setInterval(updateScheduleInfo, 60000);
});
