# Synology DS423 Docker 部署指南

適用機種：**DS423**（CPU：Realtek RTD1619B，**ARM64**）  
DSM：**7.3** 以上，使用 **Container Manager**（原 Docker）。

---

## 架構說明

| 項目 | 說明 |
|------|------|
| 容器內 | Python + Chromium + 爬蟲 + Web + 排程 |
| 持久化 | 主機資料夾 `./data` → 容器 `/app/data`（`database.db`、日誌） |
| 設定 | 主機 `.env` → 容器環境變數 |
| 網頁 | `http://NAS_IP:8000` |
| 排程 | 容器常駐時自動 08:10 / 12:00（台北時間） |

---

## 一、在 NAS 建立專案目錄

1. 開啟 **File Station**
2. 建立資料夾，例如：`/docker/pcc-scraper`
3. 將整個 `web_crawler` 專案複製到該目錄（可用 File Station 上傳或 SMB 從 PC 複製）

最終結構範例：

```
/docker/pcc-scraper/
  ├── Dockerfile
  ├── docker-compose.yml
  ├── .env              ← 自行建立（見下方）
  ├── data/             ← 【必須手動建立】存放 database.db（見下方）
  ├── app.py
  ├── run.py
  └── ...
```

### ⚠️ 重要：先建立 `data` 資料夾

Container Manager 啟動前，**一定要在 File Station 建立**：

`/docker/pcc-scraper/data`

（完整路徑通常是 `/volume1/docker/pcc-scraper/data`）

若缺少此資料夾，會出現錯誤：

`Bind mount failed: '/volume1/docker/pcc-scraper/data' does not exist`

---

## 二、建立 `.env`

在 `/docker/pcc-scraper/` 建立 `.env`（可複製 `.env.example` 後修改）：

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/你的ID/你的TOKEN

SCRAPE_SCHEDULE_HOUR=8
SCRAPE_SCHEDULE_MINUTE=10
TRACK_CHECK_HOUR=12
TRACK_CHECK_MINUTE=0

SCRAPE_LOOKBACK_DAYS=3
FILTER_KEYWORDS=網路設備,資訊設備,通訊設備,路由器,交換器,網路,資通訊,伺服器,防火牆,Switch,Router

CHROME_HEADLESS=true
APP_HOST=0.0.0.0
APP_PORT=8000
```

**請用 UTF-8 儲存**（File Station 編輯或 PC 記事本另存 UTF-8）。

---

## 三、用 Container Manager 部署（建議）

### 方法 A：Docker Compose 專案

1. 開啟 **Container Manager** → **專案** → **建立**
2. 專案名稱：`pcc-scraper`
3. 路徑：選 `/docker/pcc-scraper`
4. 來源：選 **建立 docker-compose.yml**（使用資料夾內現有檔案）
5. 勾選 **Build 映像檔**（第一次需 10～30 分鐘，ARM 較慢）
6. 建立並啟動

### 方法 B：SSH 指令（進階）

```bash
cd /volume1/docker/pcc-scraper
sudo docker compose build
sudo docker compose up -d
sudo docker compose logs -f
```

> 卷路徑可能是 `/volume1/` 或 `/volume2/`，依實際儲存空間調整。

---

## 四、驗證

1. **Container Manager** → 容器 `pcc-scraper` 狀態為「執行中」
2. 瀏覽器開啟：`http://你的NAS_IP:8000`
3. SSH 或「終端機」執行測試：

```bash
sudo docker exec -it pcc-scraper python scripts/cli.py check-network
sudo docker exec -it pcc-scraper python scripts/cli.py scrape
sudo docker exec -it pcc-scraper python scripts/cli.py list --limit 5
```

4. 檢查 Discord 是否收到通知

---

## 五、資料備份

重要檔案在主機：

- `/docker/pcc-scraper/data/database.db` — 所有案件
- `/docker/pcc-scraper/data/logs/scraper.log` — 日誌
- `/docker/pcc-scraper/.env` — 設定

可將 `data` 資料夾加入 **Hyper Backup** 定期備份。

---

## 六、常見問題

### 1. Build 失敗或很慢

- DS423 為 **ARM64**，請在 NAS 本機 Build，不要用 x86 電腦建的映像檔。
- 確保 DSM 已更新，Container Manager 為最新版。

### 2. 爬蟲失敗 / 連不上政府採購網

```bash
sudo docker exec -it pcc-scraper python scripts/cli.py check-network
```

NAS 所在網路必須能開啟 https://web.pcc.gov.tw（與 PC 相同）。

### 3. Chromium 記憶體不足

`docker-compose.yml` 已設 `shm_size: 512mb`。若仍失敗，在 Container Manager 將容器記憶體上限設為 **≥ 1GB**。

### 4. 更新程式

```bash
cd /volume1/docker/pcc-scraper
# 上傳新檔案後
sudo docker compose build --no-cache
sudo docker compose up -d
```

`data/` 內資料庫會保留。

### 5. 只要排程、不要 Web 介面

可改執行單次爬蟲（需自行改 entrypoint 或另建 cron 容器）。預設 `run.py` 會同時開 Web + 排程。

---

## 七、防火牆

若區網無法開啟 `http://NAS_IP:8000`：

**控制台** → **安全性** → **防火牆** → 允許連接埠 **8000**（或僅限區網）。

---

## 八、資源建議（DS423）

| 資源 | 建議 |
|------|------|
| RAM | 容器 ≥ 1GB |
| 儲存 | 映像檔約 1～1.5GB + 資料庫成長 |
| CPU | 爬蟲執行時 CPU 會升高，屬正常 |

---

有問題可查看日誌：

```bash
sudo docker compose logs -f --tail 100
```

或主機檔案：`data/logs/scraper.log`
