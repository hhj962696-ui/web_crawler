# 政府電子採購網 — 爬蟲與業務中台系統

本系統自動擷取 [政府電子採購網](https://web.pcc.gov.tw)「**公開徵求**」與「**公開招標**」公告，篩選資通訊案件並寫入 SQLite。除爬蟲與 Discord Webhook 推播功能外，目前已擴充為「**遠端工作網路設備銷售的自動化中台**」，全面整合了 104 企業遠端潛力探測（模組 A）、需求計算與設備匹配引擎（模組 B）、同業競品價格監控與動態報價建議（模組 C）、設備資料庫與企業通訊錄等功能。

---

## 目錄

1. [專案歷程摘要](#專案歷程摘要)
2. [需具備的技能與環境](#需具備的技能與環境)
3. [系統架構](#系統架構)
4. [已確認的產品決策](#已確認的產品決策)
5. [專案結構](#專案結構)
6. [本機 Windows 開發與測試](#本機-windows-開發與測試)
7. [Web 功能說明](#web-功能說明)
8. [資料儲存說明](#資料儲存說明)
9. [API 一覽](#api-一覽)
10. [已知問題與排除](#已知問題與排除)

---

## 專案歷程摘要

| 階段 | 名稱 | 核心功能與開發過程 |
|:---|:---|:---|
| **Phase 1** | **基礎爬蟲與公開招標** | 實作每日爬取政府採購網「公開徵求」與「公開招標」公告，支援本地 SQLite 儲存、關鍵字篩選、押標金擷取、追蹤狀態管理與 Discord 雙頻道（分流）自動通知。 |
| **Phase 2** | **104 探測器 (模組 A)** | 研發 **模組 A** 引擎，自動根據標案機關的名稱/統編至 104 人力銀行探測 WFH 遠端職缺與網管需求。評估出「遠端潛力分數」，若高於 50 分則觸發 Discord 業務頻道警報。 |
| **Phase 3** | **設備庫與通訊錄** | 建立 Web 設備管理資料庫（CRUD）與企業通訊錄。支援自動從標案承辦人萃取聯絡資訊、匯出標準 vCard 檔案（iPhone 相容）與產生手機相機可直接掃描的 QR Code。 |
| **Phase 4** | **設備匹配引擎 (模組 B)** | 研發 **模組 B** 需求計算引擎。自動根據案源規模或預估使用者數，帶入 70% 同時上線率與 2Mbps 頻寬標準，推算 VPN 隧道與頻寬需求，自動從設備庫中匹配出性價比最高的前三台設備。 |
| **Phase 5** | **報價與比價引擎 (模組 C)** | 研發 **模組 C** 動態報價引擎與競品監控。支援記錄設備歷史決標價與多通路市場價（`price_history`），並依據匹配推薦設備的**公司成本價**，結合設定的**目標毛利率**，使用專業毛利公式自動計算「建議投標標價」。 |
| **Phase 6** | **業務中台與全面整合** | 進入 **階段 6**，實作一個暗黑科技感 Glassmorphism 整合業務儀表板 `/sales`。提供統計數據與前 5 大設備熱度排行。實作 AJAX 雙滑桿微調抽屜面板，業務可即時微調估計人數與毛利率，無痛動態重算設備匹配與標價。整合每日 17:00 Discord 業務摘要推播與一鍵承辦人同步通訊錄。 |


---

## 需具備的技能與環境

- **Python 3.12+**：FastAPI, Selenium, SQLAlchemy (ORM), APScheduler
- **前端技術**：Jinja2, HTML5, Vanilla CSS, Javascript (採用現代 Glassmorphism 微光與暗色系美學，無重型 JS 框架)
- **其他套件**：`qrcode[pil]` (產生通訊錄 QR Code), `pydantic` (資料驗證)
- **資料庫**：SQLite 3 (啟用 WAL 寫入預錄日誌模式，確保高並行讀寫效能)
- **環境**：Windows 11 (本機開發) / Synology NAS Docker (生產部署)

---

## 系統架構

系統採用**模組化管線式（Pipeline）架構**，爬蟲或手動新增案件後，會自動在背景以非阻塞執行緒觸發業務管線，依序執行模組 A、B、C 評估：

```mermaid
graph TD
    subgraph 數據來源
        PCC["政府電子採購網<br>(公開徵求/公開招標)"]
        J104["104 人力銀行<br>(職缺探測)"]
    end

    subgraph 核心爬蟲與排程 (scheduler.py)
        S1["scraper.py (徵求爬蟲)"]
        S2["bidding_scraper.py (招標爬蟲)"]
    end

    subgraph 本地儲存 (SQLite 啟用 WAL)
        T_Tenders["tenders (案件表)"]
        T_Bidding["bidding_tenders (招標表)"]
        T_Insights["sales_insights (業務洞察主表)"]
        T_Contacts["org_contacts (企業通訊錄)"]
        T_Devices["devices (設備型號庫)"]
        T_Prices["price_history (價格歷史紀錄)"]
    end

    PCC --> S1
    PCC --> S2
    S1 --> T_Tenders
    S2 --> T_Bidding

    subgraph 業務中台管線 (sales_pipeline.py)
        PL["Pipeline 背景觸發控制器"]
        MA["模組 A: 104 探測器<br>(job_analyzer.py)"]
        MB["模組 B: 設備匹配引擎<br>(device_matcher.py)"]
        MC["模組 C: 動態報價引擎<br>(pricing_engine.py)"]
        CM["聯絡人自動建檔<br>(contact_manager.py)"]
    end

    T_Tenders --> PL
    T_Bidding --> PL
    
    PL --> CM
    PL --> MA
    PL --> MB
    PL --> MC

    J104 --> MA
    CM --> T_Contacts
    MA --> T_Insights
    MB --> T_Insights
    MC --> T_Insights
    T_Devices --> MB
    T_Devices --> MC
    MC --> T_Prices

    subgraph 推播與通路通知
        DN["discord_notifier.py (推播中心)"]
        DC_Ch1["Discord #公開徵求頻道"]
        DC_Ch2["Discord #公開招標頻道"]
        DC_Ch3["Discord #業務通知頻道<br>(高潛力評分 >=50)"]
    end

    S1 --> DN
    S2 --> DN
    MA -->|高潛力判定| DN
    DN --> DC_Ch1
    DN --> DC_Ch2
    DN --> DC_Ch3
```

---

## 已確認的產品決策

- **資料庫擴充不影響舊功能**：使用 `sales_insights` 獨立表紀錄所有業務推算數據，由 `tender_id` 關聯。
- **管線非阻塞執行**：爬蟲寫入資料後，使用獨立 Thread 背景觸發管線，即使 104 爬蟲或設備匹配出錯也不中斷採購網爬蟲的主流程。
- **104 搜尋策略**：機關名稱優先 → 統編備援；自動略過學校/國中小/中研院等機關以節省爬蟲資源。
- **設備匹配準則 (模組 B)**：
  - 默認帶入 **70% VPN 同時上線率**。
  - 每位遠端使用者預設配置 **2 Mbps 頻寬需求**。
  - 根據推算出的頻寬及 VPN 隧道數，自 `devices` 庫中篩選效能達標，且**成本最低**的前三台設備進行推薦，並將第一推薦設備作為銷售主推。
- **動態報價計算法 (模組 C)**：
  - 基於銷售主推設備的 **公司內部成本價 (cost_price)** 進行推算。
  - 採用業界標準毛利計算公式：`建議標價 = 成本價 / (1.0 - 目標毛利率)`，避免採用傳統「成本 * (1 + 毛利率)」而稀釋實際利潤率。
  - 支援追蹤記錄各設備在不同時間、不同渠道（市場價、競品決標價、電商價）的價格變動，以折線圖或趨勢清單呈現，為業務提供強大的比價依據。

---

## 專案結構

```text
web_crawler/
├── run.py                 # 統一啟動入口（同時載入 Web 服務與 APScheduler 排程）
├── app.py                 # FastAPI 主路由與首頁、招標、追蹤等 Web UI 渲染
├── scraper.py             # 政府採購網 —「公開徵求」爬蟲引擎
├── bidding_scraper.py     # 政府採購網 —「公開招標」爬蟲引擎
├── sales_pipeline.py      # 業務中台管線控制器（串接模組 A/B/C 的背景處理）
├── job_analyzer.py        # 模組 A：104 職缺探測與遠端工作潛力評分引擎
├── device_matcher.py      # 模組 B：網路頻寬與 VPN 需求計算、設備推薦匹配引擎
├── pricing_engine.py      # 模組 C：動態比價、價格追蹤與毛利報價估算引擎
├── contact_manager.py     # 聯絡人萃取管理、vCard 檔案生成與 QR Code 渲染
├── discord_notifier.py    # Discord 推播通知（包含徵求、招標與高潛力業務通知）
├── scheduler.py           # APScheduler 自動化定時任務管理
├── models.py              # SQLAlchemy ORM 資料庫模型定義 (SQLite 欄位結構)
├── config.py              # 系統環境變數與全域設定項目
├── routers/               # API 路由分流目錄
│   ├── devices.py         # 設備型號管理 (CRUD) API 與 UI 路由
│   ├── contacts.py        # 企業通訊錄 API 與 UI 路由
│   ├── insights.py        # 業務洞察、設備匹配與報價手動調整 API
│   └── prices.py          # 設備價格歷史記錄與趨勢查詢 API
├── templates/             # Jinja2 HTML5 網頁樣板目錄
│   ├── base.html          # 全域導覽列與玻璃擬物化佈局基礎樣板
│   ├── index.html         # 公開徵求列表與搜尋管理
│   ├── bidding.html       # 公開招標列表與押標金展示
│   ├── tracked.html       # 追蹤案件管理與備註編輯
│   ├── sales_dashboard.html # 業務中台儀表板與 AJAX 決策微調抽屜
│   ├── devices.html       # 設備庫管理面板
│   ├── contacts.html      # 企業通訊錄面板
│   └── settings.html      # 系統關鍵字、排程與 Webhook 設定面板
├── static/                # 靜態資源目錄
│   ├── css/
│   │   └── style.css      # 精美現代暗黑模式 CSS 設計系統
│   └── js/
│       └── main.js        # 前端 Toast 通知與爬蟲狀態同步邏輯
└── database.db            # 核心 SQLite 本地資料庫 (啟動時會自動完成 init 初始化)
```

---

## 本機 Windows 開發與測試

```powershell
# 進入專案目錄
cd D:\web_crawler

# 建立並啟用虛擬環境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 安裝相依套件
pip install -r requirements.txt

# 啟動系統
python run.py
```

> **提示**：系統在首次啟動時，若偵測到 `database.db` 遺漏任何新增的欄位或資料表（例如 `price_history`、`sales_insights`），會自動執行 `init_db()` 進行無損升級與表單建立。

---

## Web 功能說明

| 頁面 | 核心功能介紹 | 亮點設計 |
|:---|:---|:---|
| **公開徵求** (`/`) | 列表、關鍵字搜尋、案件追蹤、手動 Discord 推播。 | 支援關鍵字標記，過濾出資通訊高度相關案件。 |
| **業務中台** (`/sales`) | 業務中台總覽、設備推薦排行（長度熱度計）、決策微調抽屜（AJAX 雙向即時更新）、一鍵同步通訊錄、手動推送摘要。 | 高級玻璃擬態暗黑風格，純 Vanilla JS 即時互動體驗，完美閉環。 |
| **公開招標** (`/bidding`) | 展示截止投標時間、採購性質、預算與自動解析的押標金資訊。 | 提供一鍵手動補抓與推播功能。 |
| **追蹤案件** (`/tracked`) | 業務追蹤面板，可自由編輯追蹤備註與進度。 | 用戶可於此頁面展開「**業務決策面板**」，進行模組 B 與 C 的手動微調。 |
| **設備管理** (`/devices`) | 防火牆、路由器、AP 等設備型號庫，紀錄設備的 VPN 規格、吞吐量與**內部成本價**。 | 模組 B 設備匹配的基礎數據庫。 |
| **企業通訊錄** (`/contacts`) | 聯絡人管理、vCard 批次匯出、手機掃碼加入、CSV 匯出。 | 爬蟲自動萃取招標單位承辦人資訊，免手動輸入直接建檔。 |
| **系統設定** (`/settings`) | 管理爬蟲關鍵字、三個 Discord Webhooks（徵求/招標/業務高潛力）與排程執行頻率。 | 支援隨改隨用，立即生效。 |

---

## 資料儲存說明

系統擁有五張業務中台關聯表：
1. **`sales_insights`（業務洞察表）**：
   - 關聯鍵：`tender_id`（與 tenders 或 bidding_tenders 案號關聯）
   - **模組 A**：`remote_score` (遠端分數), `remote_job_count` (遠端職缺數), `netadmin_job_count` (網管職缺數), `job_analysis_json` (職缺明細 JSON)
   - **模組 B**：`estimated_users` (預估使用者數), `vpn_bandwidth_mbps` (推算頻寬), `recommended_devices_json` (推薦設備 JSON), `device_match_reason` (推薦原因說明)
   - **模組 C**：`market_price` (參考市場價), `suggested_bid_price` (建議標價), `margin_rate` (目標毛利率，預設 "0.15"), `price_source` (計價基準說明)
2. **`devices`（設備型號庫）**：
   - 紀錄 `brand` (品牌), `model` (型號), `max_vpn_tunnels` (最大 VPN 通道數), `throughput_mbps` (吞吐量), `reference_price` (參考售價), `cost_price` (內部成本價), `features` (規格特色)
3. **`price_history`（價格歷史表）**：
   - 紀錄設備價格歷史軌跡。`price_type` 支援 `market` (市場參考價)、`bid_award` (歷史招標決標價) 及 `ecommerce` (電商促銷價)。
4. **`org_contacts`（企業通訊錄）**：
   - 紀錄從招標文件自動萃取或手動新增的機關聯絡人（姓名、電話、手機、電子信箱、部門職稱及所屬案號）。
5. **`analysis_logs`（分析執行紀錄）**：
   - 紀錄管線模組的執行狀態、耗時及錯誤日誌（分為 `job104`、`device`、`pricing` 模組）。

---

## API 一覽

### 1. 設備匹配與業務洞察 API (routers/insights.py & app.py)

| 方法 | 路徑 | 參數 | 說明 |
|:---|:---|:---|:---|
| GET | `/api/sales/dashboard` | 無 | 取得業務中台統計數據與最熱門設備排行前 5 名。 |
| GET | `/api/sales/insights` | Query: `page` (int), `potential` (str), `status` (str), `sort` (str), `search` (str) | 取得所有案件的業務洞察列表，支援高潛力/待報價篩選、客製預算與分數排序、關鍵字搜尋。 |
| GET | `/api/insights/{tender_id}` | 路徑參數 `tender_id` | 取得特定案件的完整業務評估資料（含潛力分、推薦設備、建議標價）。 |
| POST | `/api/insights/{tender_id}/match-device` | JSON: `{"estimated_users": int, "budget": float}` | 手動輸入或變更預估使用者人數，重新計算 VPN 頻寬並匹配推薦設備。 |
| POST | `/api/insights/{tender_id}/calculate-price` | JSON: `{"margin_rate": float}` | 調整目標利潤率（例如 `0.20` 代表 20% 毛利），動態計算建議標價。 |
| POST | `/api/sales/insights/{tender_id}/push` | 路徑參數 `tender_id` | 手動推送特定標案的詳細業務洞察卡片至業務 Discord 頻道。 |
| POST | `/api/sales/summary/push` | 無 | 手動立即向 Discord 業務頻道發送本日業務摘要推播。 |


### 2. 設備價格與競品監控 API (routers/prices.py)

| 方法 | 路徑 | 參數 | 說明 |
|:---|:---|:---|:---|
| GET | `/api/prices/history` | Query: `device_id` (int), `days` (int) | 取得特定設備在過去 N 天內的價格變動歷史趨勢，供前端繪製比價圖表。 |
| POST | `/api/prices/record` | JSON: `{"device_id": int, "price": float, "price_type": str}` | 手動或經由外部 API 記錄新的參考市場價、歷史決標價或電商售價。 |

### 3. 設備與通訊錄 API (routers/devices.py & routers/contacts.py)

| 方法 | 路徑 | 參數 | 說明 |
|:---|:---|:---|:---|
| GET | `/api/devices` | 無 | 取得系統內所有作用中的設備型號清單。 |
| POST | `/api/devices` | JSON 設備屬性 | 新增設備型號至資料庫。 |
| GET | `/api/contacts` | 無 | 取得通訊錄名單。 |
| POST | `/api/contacts/sync` | 無 | 從現有標案自動同步並去重萃取承辦人至通訊錄檔案。 |
| GET | `/api/contacts/export-vcard` | 無 | 將通訊錄內所有聯絡人打包成 `.vcf` 格式檔案下載。 |
| GET | `/api/contacts/{id}/qrcode` | 路徑參數 `id` | 產生該聯絡人專屬的 vCard QR Code 圖片，供手機掃描快速加入。 |
| GET | `/api/contacts/export-csv` | 無 | 匯出通訊錄為 CSV 檔案。 |

### 4. 系統與爬蟲核心 API (app.py)

| 方法 | 路徑 | 參數 | 說明 |
|:---|:---|:---|:---|
| POST | `/api/scrape/run` | 無 | 觸發「公開徵求」即時爬蟲（背景異步執行）。 |
| POST | `/api/scrape/run-bidding` | 無 | 觸發「公開招標」即時爬蟲（背景異步執行）。 |
| POST | `/api/job104/manual` | 無 | 手動觸發 104 人力銀行探測器分析（背景批次處理）。 |
| GET | `/api/scrape/status` | 無 | 查詢當前是否有爬蟲或分析管線正在背景執行。 |

---

## 已知問題與排除

1. **Selenium 驅動問題**：爬蟲與 104 探測器需要 Chrome 瀏覽器。若伺服器未安裝 Chrome，系統會自動切換為備用的 headless 模擬模式。本機 Windows 開發環境請確保 Chrome 瀏覽器已更新至最新版。
2. **SQLite 鎖定 (Database is locked)**：因為爬蟲與 Web 服務可能同時寫入資料庫，本系統已全域啟用 **PRAGMA journal_mode=WAL**。此模式允許讀寫並行，大幅降低資料庫鎖定機率。
3. **104 爬蟲 IP 阻擋**：頻繁手動執行 104 探測可能觸發防爬機制。系統已內建隨機延遲（Random Delay）與請求標頭混淆機制。建議維持每日定時排程執行即可，避免高頻率手動重試。

---
*最後更新時間：2026-05-21 — 全面完成模組 A、B、C 研發，打通「採購網爬取 ➜ 104 潛力探測 ➜ 設備需求匹配 ➜ 動態毛利報價」的自動化業務閉環。*
