# NBA Score Board

NBA 資料儀表板，包含三個頁面：

- **比賽**：今日即時比分（進行中的比賽每 30 秒自動更新），也可查詢任意日期的賽果
- **球隊**：東西區戰績榜，以及各隊的本季數據排名、每場得失分差、近期賽果與球員名單
- **球員**：搜尋球員，查看基本資料、生涯平均與逐季數據

前端是 React（Create React App），後端是 FastAPI，資料來自 [nba_api](https://github.com/swar/nba_api)。

## 比賽頁的日期選擇

- **日期列**：頁面上方顯示所選日期前後共 7 天（手機上 5 天），點一下就切換到該天；`‹` `›` 前後移動一天，「今天」標示目前即時比分所在的日期
- **跳到任意日期**：右上角的日期欄位可以直接選日期，「今天」按鈕回到即時比分
- **網址會記住日期**：例如 `#/games/2026-11-20`，重新整理或分享連結都會停在同一天；`#/games` 則是今天
- **日期是美國當地日期**：NBA 以美國日期排賽程，所以在台灣看到的「今天」常常是台灣的前一天
- **開賽時間換算成你的時區**，並附上日期，例如美國 11/25 晚上的比賽會顯示「11/26 上午08:00」

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
| `GET /games/?date=YYYY-MM-DD` | 指定日期（美國日期）的比賽；格式錯誤回傳 400 |
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
- **後端回傳 502 `NBA API request failed`**：NBA 官方網站連線失敗或逾時（後端已自動重試一次）。NBA 會封鎖部分網路（例如雲端主機、某些 VPN），請換個網路再試。
- **比賽資料沒有馬上更新**：後端會暫存結果以減少對 NBA 的請求——今天的即時比分 15 秒、還有比賽沒打完的日期 60 秒、全部打完的日期 6 小時。重新啟動後端即可清除。
- **選「今天」看到的日期比台灣早一天**：這是正常的，日期依美國當地日期計算，台灣上午到下午之間通常會差一天。
- **球員大頭照或球隊 logo 沒顯示**：圖片直接從 NBA 的 CDN 載入，被封鎖時會自動隱藏，不影響其他資料。
