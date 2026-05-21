# 政府電子採購網 — 公開徵求／公開招標爬蟲系統

本地端自動擷取 [政府電子採購網](https://web.pcc.gov.tw)「**公開徵求**」與「**公開招標**」公告，篩選資通訊相關案件，寫入 SQLite，並透過 Discord Webhook 推送；提供 Web 介面瀏覽、追蹤與手動推送。

> **給新對話的 AI / 開發者**：本文記錄從零到目前為止的決策、架構與操作方式。下一階段預計：**本機測試完成後，持續驗證 NAS（Synology DS423）部署**。

---

## 目錄

1. [專案歷程摘要](#專案歷程摘要)
2. [需具備的技能與環境](#需具備的技能與環境)
3. [系統架構](#系統架構)
4. [已確認的產品決策](#已確認的產品決策)
5. [專案結構](#專案結構)
6. [本機 Windows 開發與測試](#本機-windows-開發與測試)
7. [命令列工具 CLI](#命令列工具-cli)
8. [Synology NAS Docker 部署](#synology-nas-docker-部署)
9. [Web 功能說明](#web-功能說明)
10. [資料儲存說明](#資料儲存說明)
11. [API 一覽](#api-一覽)
12. [已知問題與排除](#已知問題與排除)
13. [下一階段測試建議](#下一階段測試建議)

---

## 專案歷程摘要

| 階段 | 內容 |
|------|------|
| 需求評估 | 每日爬政府採購網公開徵求、Discord 通知、本地 Web + SQLite、追蹤狀態、關鍵字篩選 |
| 初版實作 | FastAPI + Selenium + SQLite + APScheduler + Discord Embed |
| 連線問題 | 本機/NAS 需能連 `web.pcc.gov.tw`；新增 `network_check.py`、`cli check-network` |
| 編碼問題 | `.env` 須 UTF-8；`load_dotenv(encoding="utf-8")` |
| 承辦人/電話 N/A | 列表頁未擷取「檢視」連結；改抓 `urlSelector/common/tpAppeal?pk=...` 詳情頁 |
| Discord 排版 | 與 CLI 列表一致；手動 `notify-preview`；台北時區 timestamp |
| 網頁 UX | 手動爬蟲按鈕換頁後狀態同步（`syncScrapeButtonState`） |
| 手動推送 | 每案「📤 推送」按鈕 → `POST /api/tenders/{id}/push-discord` |
| NAS | DS423（ARM64）Dockerfile + docker-compose；`data/` 資料夾必須先建立 |
| 本機驗證 | `python run.py` 成功運行於 `http://127.0.0.1:8000`（**不需 XAMPP**） |
| **公開招標** | `bidding_scraper.py`、`bidding_tenders` 表、Web「公開招標」分頁、排程 09:00 |
| **Discord 分流** | 徵求 `DISCORD_WEBHOOK_URL`；招標 `BIDDING_DISCORD_WEBHOOK_URL`，Embed 標題區分 |
| **案號同步** | 同案號先徵求後招標 → `tenders.status` 更新為「公開招標」 |
| **手動爬蟲** | 頂部拆成「手動徵求爬蟲」「手動招標爬蟲」 |
| **電話欄位** | 詳情頁誤抓長文修正；`repair-phones` / `enrich-bidding` |
| **設定頁擴充** | 招標排程、採購性質（工程/財物/勞務）、招標 Webhook |
| **Bug 修復** | `config.BASE_DIR` 缺失導致儲存 Webhook 500 |
| **運作檢測** | 新增每日 08:00 自動推播 Discord 系統健康狀態檢查 (`discord_notifier.py` / `HEALTH_CHECK_HOUR`) |
| **押標金抓取** | 爬蟲新增擷取「押標金」（`bid_bond`）並自動格式化金額，同步顯示於 Web UI 與 Discord 推播中 |
| **UI 優化** | 設定頁 Discord Webhook 輸入框版面微調、顯示/隱藏密碼功能修復、並為兩個頻道獨立加上測試通知按鈕 |

---

## 需具備的技能與環境

### 技能（Skill / 知識）

| 領域 | 內容 |
|------|------|
| **Python** | 虛擬環境、pip、`async` 基礎（FastAPI） |
| **Web 爬蟲** | Selenium、BeautifulSoup、分頁、詳情頁解析、禮貌延遲與重試 |
| **後端** | FastAPI、Jinja2 模板、REST API |
| **資料庫** | SQLite + SQLAlchemy（**不需 MariaDB**） |
| **排程** | APScheduler（cron 風格，Asia/Taipei） |
| **Discord** | Webhook、Embed 格式、訊息分批（每則最多 5 個 Embed） |
| **Docker** | Dockerfile、docker-compose、volume 掛載、ARM64 映像 |
| **Synology** | Container Manager、專案建置、File Station（**非** XAMPP） |
| **網路** | 確認能否連政府採購網；Proxy 設定（`.env`） |
| **編碼** | Windows 下 `.env` 必須 UTF-8，避免中文關鍵字亂碼 |

### 本機環境

- Windows 10/11
- Python 3.12+
- Google Chrome（Selenium 用）
- PowerShell

### NAS 環境（已規劃）

- **Synology DS423**，DSM 7.3，CPU：Realtek RTD1619B（**ARM64**）
- Container Manager（Docker）
- 路徑範例：`/volume1/docker/pcc-scraper`
- NAS IP 範例：`192.168.0.234`

---

## 系統架構

```
政府電子採購網
  ├─ readTpAppeal（公開徵求）  ──► scraper.py       ──► tenders
  └─ readTenderBasic（公開招標）──► bidding_scraper.py ──► bidding_tenders
              │
              ▼ Selenium + Chromium（列表 + 詳情頁補抓）
        關鍵字篩選（共用 FILTER_KEYWORDS）
              │
              ├──────────────► discord_notifier.py ──► Discord Webhook（徵求 / 招標分流）
              │
              └──────────────► FastAPI Web UI ──► 瀏覽器 :8000

排程 (scheduler.py):
  - 每日 08:10 公開徵求爬蟲 (SCRAPE_SCHEDULE_*)
  - 每日 09:00 公開招標爬蟲 (BIDDING_SCHEDULE_*)
  - 每日 12:00 追蹤檢查 (TRACK_CHECK_*)
```

**啟動入口**：`run.py`（資料庫初始化 → 排程器 → Uvicorn）

---

## 已確認的產品決策

| 項目 | 決策 |
|------|------|
| 爬取範圍 | 滾動 **近 3 天**（含今天），案號去重 |
| 篩選 | 案名 + 機關名稱 **OR** 關鍵字（徵求、招標共用 `FILTER_KEYWORDS`） |
| 詳情補抓 | **新案**缺欄位時進詳情頁；既有案可 `enrich` / `enrich-bidding` |
| Discord 新案 | 僅**首次入庫**推送；0 新案不通知 |
| Discord 格式 | Embed；每則最多 5 筆（`DISCORD_EMBED_BATCH_SIZE`） |
| Discord 分流 | 徵求、招標使用**不同 Webhook**；Embed 標題區分 |
| 手動推送 | 標題「📤 手動推送案件」，招標為「📤 手動推送案件（公開招標）」 |
| 追蹤監控 | 12:00 檢查狀態（已決標/廢標/流標/已截止等） |
| 資料庫 | **SQLite**，`data/database.db`（Docker）或專案根目錄（本機） |
| 公開招標資料 | 獨立表 `bidding_tenders`，Web 獨立分頁 `/bidding` |
| 招標採購性質 | 可選工程/財物/勞務（`BIDDING_PROC_CATEGORIES`）；留空=不限 |
| 案號跨階段 | 徵求→招標視為同一案，更新 `tenders.status` 為「公開招標」 |
| 預算 | 公開徵求階段常為「未公告」，屬正常 |
| 時區 | Asia/Taipei |

---

## 專案結構

```
web_crawler/
├── run.py                 # 統一啟動（Web + 排程）
├── app.py                 # FastAPI 路由與 Web UI
├── scraper.py             # 公開徵求爬蟲（列表/詳情/補抓）
├── bidding_scraper.py     # 公開招標爬蟲
├── discord_notifier.py    # Discord 通知
├── scheduler.py           # APScheduler
├── models.py              # SQLAlchemy 模型（tenders / bidding_tenders）
├── config.py              # 設定（讀 .env）
├── network_check.py       # 政府採購網連線檢測
├── time_utils.py          # 台北時區
├── requirements.txt
├── .env.example           # 設定範本（複製為 .env）
├── database.db            # 本機 SQLite（執行後產生）
├── data/                  # Docker 持久化目錄（NAS 必建）
│   └── .gitkeep
├── logs/                  # 本機日誌
├── templates/
│   ├── index.html         # 公開徵求列表
│   ├── bidding.html       # 公開招標列表
│   ├── tracked.html
│   ├── settings.html
│   └── base.html
├── static/                # CSS / JS
├── scripts/
│   ├── cli.py             # 命令列工具
│   ├── run_scrape_once.py # 單次爬蟲（排程用）
│   ├── start_app.bat      # Windows 啟動
│   └── test.bat           # 互動選單
├── docker/
│   └── entrypoint.sh
├── Dockerfile             # ARM64 + Chromium
├── docker-compose.yml
└── docs/
    └── SYNOLOGY_DOCKER.md # NAS 詳細部署
```

---

## 本機 Windows 開發與測試

### 與 XAMPP 的關係

**不需要 XAMPP。** 本專案為 Python FastAPI，埠號 **8000**，與 XAMPP（80/443）無關。

### 第一次設定

```powershell
cd D:\web_crawler
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 編輯 .env：DISCORD_WEBHOOK_URL、BIDDING_DISCORD_WEBHOOK_URL、FILTER_KEYWORDS 等（UTF-8 存檔）
```

### 啟動（終端機需保持開啟）

```powershell
cd D:\web_crawler
.\venv\Scripts\Activate.ps1
python run.py
```

瀏覽器：**http://127.0.0.1:8000**

成功訊息含：`Uvicorn running on http://127.0.0.1:8000`  
排程 log 應顯示：公開徵求 08:10、公開招標 09:00、追蹤檢查 12:00

### 建議測試清單（本機）

- [ ] 公開徵求、公開招標分頁載入
- [ ] 設定頁 → Discord 測試通知（徵求 Webhook）
- [ ] 手動徵求 / 手動招標爬蟲 → 列表有資料
- [ ] 承辦人/電話非 N/A（異常電話可跑 `repair-phones`）
- [ ] 📤 推送單案到 Discord（徵求、招標各測一次）
- [ ] ☆ 追蹤 → 追蹤分頁
- [ ] 匯出 CSV（徵求、招標）
- [ ] 設定頁儲存招標 Webhook、採購性質、排程

---

## 命令列工具 CLI

不需瀏覽器時使用（`run.py` 可不開）：

```powershell
.\venv\Scripts\python.exe scripts\cli.py status
.\venv\Scripts\python.exe scripts\cli.py check-network
.\venv\Scripts\python.exe scripts\cli.py test-discord

# 公開徵求
.\venv\Scripts\python.exe scripts\cli.py scrape
.\venv\Scripts\python.exe scripts\cli.py enrich              # 補抓徵求承辦人/電話
.\venv\Scripts\python.exe scripts\cli.py list --limit 10

# 公開招標
.\venv\Scripts\python.exe scripts\cli.py scrape-bidding
.\venv\Scripts\python.exe scripts\cli.py enrich-bidding      # 補抓招標承辦人/電話
.\venv\Scripts\python.exe scripts\cli.py list-bidding --limit 10

# 電話修正（徵求 + 招標，不需重新爬蟲）
.\venv\Scripts\python.exe scripts\cli.py repair-phones

# 其他
.\venv\Scripts\python.exe scripts\cli.py notify-preview --limit 5
.\venv\Scripts\python.exe scripts\cli.py export -o tenders.csv
.\venv\Scripts\python.exe scripts\cli.py check-tracked
```

> **注意**：`enrich` 只處理 `tenders`（公開徵求）；公開招標請用 `enrich-bidding` 或 `repair-phones`。

---

## Synology NAS Docker 部署

詳見：**[docs/SYNOLOGY_DOCKER.md](docs/SYNOLOGY_DOCKER.md)**

### 快速要點

1. 複製專案到 `/docker/pcc-scraper`（或 `/volume1/docker/pcc-scraper`）
2. **必須先建立** `data` 資料夾（否則 `Bind mount failed ... data does not exist`）
3. 建立 `.env`（UTF-8），勿提交 Git（含雙 Webhook）
4. Container Manager → 專案 → Build → 啟動
5. 瀏覽器：`http://NAS_IP:8000`
6. **不要用 Windows PowerShell 的 `sudo`**；UNC 路徑僅能複製檔案

### 更新程式到 NAS（保留資料）

| 複製 | 不覆蓋 |
|------|--------|
| `*.py`、`templates/`、`static/`、`docker/`、`Dockerfile`、`docker-compose.yml` | `data/`、`database.db`、`.env` |

有改 Python/Dockerfile → `docker compose build` 後 `up -d`  
只改前端 → 重啟容器 + 瀏覽器 Ctrl+F5

---

## Web 功能說明

| 頁面 | 功能 |
|------|------|
| 公開徵求 (`/`) | 列表、搜尋篩選、追蹤、推送 Discord、匯出 CSV |
| **公開招標 (`/bidding`)** | 列表、搜尋、推送招標 Discord、匯出 CSV |
| 追蹤案件 | 已追蹤列表、備註、立即檢查狀態 |
| 系統設定 | 關鍵字、徵求/招標排程、採購性質、雙 Webhook、執行紀錄 |

頂部按鈕：**手動徵求爬蟲**、**手動招標爬蟲**（背景執行，換頁會透過 API 同步「執行中」狀態）

---

## 資料儲存說明

| 表 / 檔案 | 說明 |
|-----------|------|
| `tenders` | 公開徵求案件 |
| `bidding_tenders` | 公開招標案件（含採購性質、截止投標） |
| `scrape_logs` | 每次爬蟲執行紀錄（含 `daily` / `bidding_daily` / `manual` 等） |
| `.env` | 密鑰與排程（**勿 commit**） |

**不需要 MariaDB。** 備份 `data/` 或 `database.db` 即可。

---

## API 一覽

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/` | 公開徵求列表 |
| GET | `/bidding` | 公開招標列表 |
| GET | `/tracked` | 追蹤頁 |
| GET | `/settings` | 設定頁 |
| POST | `/api/scrape/run` | 手動徵求爬蟲 |
| POST | `/api/scrape/run-bidding` | 手動招標爬蟲 |
| GET | `/api/scrape/status` | 爬蟲執行狀態（含 mode） |
| POST | `/api/tenders/{id}/track` | 切換追蹤 |
| POST | `/api/tenders/{id}/push-discord` | 手動推送徵求案件 |
| POST | `/api/bidding/{id}/push-discord` | 手動推送招標案件 |
| GET | `/api/export/csv` | 匯出徵求 CSV |
| GET | `/api/export/bidding-csv` | 匯出招標 CSV |
| PUT | `/api/settings/bidding-webhook` | 招標 Webhook |
| PUT | `/api/settings/bidding-proc` | 招標採購性質 |
| POST | `/api/settings/test-webhook` | 測試徵求 Webhook |

---

## 已知問題與排除

| 現象 | 原因 | 處理 |
|------|------|------|
| Discord 關鍵字亂碼 | `.env` 非 UTF-8 | 用 UTF-8 重存 `.env` |
| 承辦人/電話 N/A | 未進詳情頁 | 重跑 `scrape` + `enrich` 或 `scrape-bidding` + `enrich-bidding` |
| 電話欄位整段投標須知 | 詳情頁誤配長文本 | `repair-phones`；新爬入案件已自動清洗 |
| `enrich` 後招標沒變 | `enrich` 只處理 `tenders` | 改用 `enrich-bidding` 或 `repair-phones` |
| 儲存招標 Webhook 500 | `config.BASE_DIR` 未定义 | 已修；重啟 `run.py` |
| `no such table: tenders` | 未 init DB | `cli status` 會自動建表 |
| 本機 8000 無法連線 | 未執行 `run.py` | 保持 `python run.py` 視窗開啟 |
| NAS bind mount 失敗 | 無 `data/` | File Station 建立 `data` |
| SSL / net_error -101 | 網路無法連採購網 | `cli check-network`、換網路/Proxy |
| 按鈕換頁變回「手動執行」 | 前端狀態未同步 | 已修 `syncScrapeButtonState` |
| 執行紀錄一直 `running` | 爬蟲中斷 | 看 `logs/scraper.log`，重啟服務 |

---

## 下一階段測試建議

給新對話的檢查清單：

### A. NAS 端驗證

- [ ] 容器穩定運行 24h
- [ ] 次日 08:10 公開徵求 + Discord 新案通知
- [ ] 次日 09:00 公開招標 + Discord 新案通知（招標頻道）
- [ ] 12:00 追蹤狀態檢查
- [ ] `data/database.db` 持久化（重啟容器資料仍在）
- [ ] 本機更新檔案後 NAS rebuild/restart 流程

### B. 功能回歸

- [ ] 手動推送、自動新案 Embed 格式一致（徵求 / 招標）
- [ ] 時間顯示為台北時間
- [ ] 關鍵字篩選是否符合預期（可調 `FILTER_KEYWORDS`）
- [ ] 招標採購性質篩選（工程/財物/勞務）
- [ ] `repair-phones` 修正異常電話

### C. 可選增強（尚未實作）

- 公開徵求**起訖日期**顯示於 Discord / 網頁
- 高預算 @mention
- 登入保護 Web
- 每日 0 新案摘要通知

---

## 環境變數參考

見 [.env.example](.env.example)。重要項目：

```env
# Discord（徵求 / 招標分流）
DISCORD_WEBHOOK_URL=...
BIDDING_DISCORD_WEBHOOK_URL=...

# 排程
SCRAPE_SCHEDULE_HOUR=8
SCRAPE_SCHEDULE_MINUTE=10
BIDDING_SCHEDULE_HOUR=9
BIDDING_SCHEDULE_MINUTE=0
TRACK_CHECK_HOUR=12
TRACK_CHECK_MINUTE=0

# 回溯天數
SCRAPE_LOOKBACK_DAYS=3
BIDDING_LOOKBACK_DAYS=3

# 招標採購性質（留空=工程+財物+勞務全要）
# BIDDING_PROC_CATEGORIES=財物,勞務

FILTER_KEYWORDS=網路設備,資訊設備,...
APP_HOST=127.0.0.1          # NAS Docker 用 0.0.0.0
APP_PORT=8000
CHROME_HEADLESS=true
```

---

## 授權與免責

僅供個人/內部監控政府公開資料使用。請遵守政府電子採購網使用條款，合理控制爬取頻率。Webhook URL 切勿公開或提交版本庫。

---

*最後更新：2026-05-21 — 新增押標金欄位擷取與金額自動格式化、每日 08:00 自動健康檢測通知、Web UI 設定頁面優化。*
