# NBA Score Board

NBA 資料儀表板，包含三個頁面：

- **比賽**：今日即時比分（進行中的比賽每 30 秒自動更新），也可查詢任意日期的賽果
- **球隊**：東西區戰績榜，以及各隊的本季數據排名、每場得失分差、近期賽果與球員名單
- **球員**：搜尋球員，查看基本資料、生涯平均與逐季數據

前端是 React（Create React App），後端是 FastAPI，資料來自 [nba_api](https://github.com/swar/nba_api)。

## 需求

- Python 3.10 以上
- Node.js 18 以上

## 啟動

前後端要各開一個終端機同時執行。

### 1. 後端（FastAPI，port 8000）

第一次執行先建立虛擬環境並安裝套件：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

啟動：

```bash
cd src/api
../../.venv/bin/uvicorn main:app --reload --port 8000
```

啟動後可以打開 <http://localhost:8000/docs> 查看與測試所有 API。

> 用 VS Code 的話，先把 Python 直譯器選成 `.venv/bin/python`，再用「Run and Debug」裡的 **Python Debugger: FastAPI** 啟動，效果相同。

### 2. 前端（React，port 3000）

第一次執行先安裝套件：

```bash
npm install
```

啟動：

```bash
npm start
```

打開 <http://localhost:3000>。前端對 API 的請求會透過 `package.json` 裡的 `proxy` 轉到 `http://localhost:8000`，所以**後端必須先啟動**，否則頁面會顯示無法取得資料。

## API

| 路徑 | 說明 |
| --- | --- |
| `GET /games/` | 今日比賽（即時比分） |
| `GET /games/?date=YYYY-MM-DD` | 指定日期的比賽 |
| `GET /team/standings` | 本季東西區戰績 |
| `GET /team/{team_id}/profile` | 球隊資料、數據排名、賽果與球員名單 |
| `GET /team/{abbr}` | 以縮寫查詢球隊，例如 `BOS` |
| `GET /player/?active=true` | 球員名單（`active` 省略則包含退役球員） |
| `GET /player/{player_id}/profile` | 球員資料與逐季數據 |
| `GET /player/{name}` | 以全名搜尋球員 |

## 測試與建置

```bash
npm test          # 前端測試（watch 模式；加上 CI=true 只跑一次）
npm run build     # 建置正式版到 build/
```

## 常見問題

- **頁面顯示「無法取得…資料」、終端機出現 `Proxy error ... ECONNREFUSED`**：後端沒有啟動，照上面步驟啟動後端後重新整理。
- **後端回傳 502 `NBA API request failed`**：NBA 官方網站連線失敗或逾時。NBA 會封鎖部分網路（例如雲端主機、某些 VPN），請換個網路再試。
- **球員大頭照或球隊 logo 沒顯示**：圖片直接從 NBA 的 CDN 載入，被封鎖時會自動隱藏，不影響其他資料。
