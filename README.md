# 政府電子採購網 — 爬蟲與業務中台系統

本系統自動擷取 [政府電子採購網](https://web.pcc.gov.tw)「**公開徵求**」與「**公開招標**」公告，篩選資通訊案件並寫入 SQLite。除爬蟲與 Discord Webhook 推播功能外，目前已擴充為「**遠端工作網路設備銷售的自動化中台**」，包含 104 人力銀行企業遠端潛力探測、設備管理庫與企業通訊錄整合功能。

> **給新對話的 AI / 開發者**：本文記錄從零到目前為止的決策、架構與操作方式。下一階段預計：**實作模組 B（需求計算與設備匹配引擎）與模組 C（報價引擎）**。

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

| 階段 | 內容 |
|------|------|
| 基礎爬蟲 | 每日爬政府採購網、Discord 通知、本地 Web + SQLite、追蹤狀態、關鍵字篩選 |
| 公開招標 | `bidding_tenders` 表、Web「公開招標」分頁、Discord 分流、押標金抓取 |
| **中台擴充 (P1)** | 新增 5 張業務關聯表（`sales_insights`, `devices`, `org_contacts` 等）、`sales_pipeline.py` 觸發管線 |
| **104 探測器 (P2)**| 實作模組 A：自動去 104 爬取標案單位的職缺，計算「遠端/網管」潛力分數。高分 (>=50) 自動觸發業務頻道 Discord 警報。 |
| **設備與通訊錄 (P3)**| 新增 Web 設備資料庫 (CRUD) 與企業通訊錄，支援 iPhone vCard 與 QRCode 掃描。爬蟲自動萃取聯絡人同步至通訊錄。 |

---

## 需具備的技能與環境

- **Python 3.12+**：FastAPI, Selenium, SQLAlchemy, APScheduler
- **前端技術**：Jinja2, HTML, Vanilla CSS, JS (無重型框架)
- **其他套件**：`qrcode[pil]` (產生通訊錄 QR Code)
- **環境**：Windows (本機開發) / Synology NAS Docker (部署)

---

## 系統架構

```text
【爬蟲層】
政府採購網 ──► scraper.py / bidding_scraper.py ──► tenders / bidding_tenders
                        │
                        ▼ (自動觸發 / 手動觸發)
【業務管線層 sales_pipeline.py】
  ├──► 同步聯絡人 (contact_manager.py) ──► org_contacts (自動建檔)
  └──► 模組 A：104 探測器 (job_analyzer.py) 
         ├── 搜尋 104 職缺
         ├── 計算遠端/網管潛力分數 ──► sales_insights
         └── 若高潛力 ──► discord_notifier.py ──► 業務 Discord Webhook

【排程管理 scheduler.py】
  - 08:10 公開徵求爬蟲
  - 09:00 公開招標爬蟲
  - 10:00 104 人力銀行探測器批次分析
  - 12:00 追蹤狀態檢查
```

---

## 已確認的產品決策

- **資料庫擴充不影響舊功能**：使用 `sales_insights` 獨立表紀錄所有業務推算數據，由 `tender_id` 關聯。
- **管線非阻塞執行**：爬蟲寫入資料後，使用獨立 Thread 背景觸發管線，即使 104 爬蟲出錯也不中斷採購網爬蟲。
- **104 搜尋策略**：機關名稱優先 → 統編備援；自動略過學校/國中小/中研院等機關以節省資源。
- **通訊錄整合**：為方便業務外訪，系統自動產生 vCard (v3.0) 格式，提供 QR Code 讓 iPhone 相機直接掃描加入聯絡人。

---

## 專案結構

```
web_crawler/
├── run.py                 # 統一啟動（Web + 排程）
├── app.py                 # FastAPI 路由與 Web UI
├── scraper.py / bidding_scraper.py # 政府採購網爬蟲
├── sales_pipeline.py      # 業務中台管線入口
├── job_analyzer.py        # 模組 A：104 探測器與評分引擎
├── contact_manager.py     # 通訊錄同步、vCard 與 QRCode 產生
├── discord_notifier.py    # Discord 系統與業務通知
├── scheduler.py           # APScheduler 排程管理
├── models.py              # SQLAlchemy 模型定義
├── routers/               # (新增) API 分流
│   ├── devices.py         # 設備管理路由
│   └── contacts.py        # 企業通訊錄路由
├── templates/             # HTML 樣板 (index, bidding, devices, contacts...)
└── database.db            # SQLite 資料庫 (自動建立)
```

---

## 本機 Windows 開發與測試

```powershell
cd D:\web_crawler
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```
> **注意**：如果剛 pull 最新程式碼，`run.py` 啟動時會自動執行 `init_db()` 建立所有遺漏的資料表。

---

## Web 功能說明

| 頁面 | 功能 |
|------|------|
| **公開徵求** (`/`) | 列表、搜尋、追蹤、手動推播 |
| **公開招標** (`/bidding`) | 列表、搜尋、手動推播 |
| **追蹤案件** (`/tracked`) | 已追蹤案件列表與狀態追蹤 |
| **設備管理** (`/devices`) | 設備型號資料庫 (CRUD)，紀錄參考價與規格 |
| **企業通訊錄** (`/contacts`) | 聯絡人管理、vCard 批次匯出、手機掃碼加入、CSV 匯出 |
| **系統設定** (`/settings`) | 關鍵字、三個 Discord Webhooks (徵求/招標/業務)、排程時間設定 |

---

## 資料儲存說明

新增的 5 張業務表單：
- `sales_insights`：整合模組 A/B/C 分析結果（分數、預估人數、建議報價等）。
- `devices`：設備型號資料庫。
- `price_history`：價格歷史紀錄。
- `org_contacts`：企業通訊錄（支援從爬蟲自動進件）。
- `analysis_logs`：管線與 104 分析執行紀錄。

---

## API 一覽

*除既有的爬蟲 API 外，新增的中台 API：*

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/job104/manual` | 手動觸發 104 探測器批次分析 |
| GET  | `/api/devices` | 取得設備列表 (JSON) |
| POST | `/api/devices` | 新增設備 |
| GET  | `/api/contacts` | 取得聯絡人列表 (JSON) |
| GET  | `/api/contacts/export-vcard` | 匯出全部聯絡人為 .vcf 檔案 |
| GET  | `/api/contacts/{id}/qrcode` | 產生單一聯絡人的 vCard QR Code (圖片) |
| GET  | `/api/contacts/export-csv` | 匯出通訊錄為 CSV |

---

*最後更新：2026-05-21 — 完成模組 A (104 探測器)、設備管理庫與企業通訊錄 vCard/QRCode 整合。*
