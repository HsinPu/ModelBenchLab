# v0.1 驗證紀錄

驗證日期：2026-09-22。環境：Windows、Python 3.12、本機 SQLite、獨立背景 Worker。

## 已通過
- `python -m pytest -q`：15 passed；Windows 暫存 SQLite 連線清理已修正。
- `python -m pip check`：No broken requirements found。
- `npm run build`：TypeScript 檢查與 Vite 正式建置通過。
- `docker compose config --quiet`：Compose 設定解析通過。
- PowerShell 啟動腳本實測成功；偵測到 5173 已被其他服務使用，透過 `-FrontendPort 5175` 啟動，未停止其他服務。
- 瀏覽器實測：建立「第一版驗收 · 雙模型比較」，10 題 × 2 模型共 20 筆工作全部完成，SSE 更新成功。
- Demo / Stable 自動規則 9/9；Demo / Experimental 6/9；兩個摘要回答保留人工評分。
- 瀏覽器實測：未通過 / 人工評分篩選、保存 4/5 人工評分與註記、模型連線測試、題庫版本編輯入口。
- 總覽與結果比較頁已查看實際截圖；修正篩選選單擠壓標題的版面問題。

## 測試覆蓋
完整建立與執行、快照 / 金鑰不外洩、重複派送、取消待執行工作、取消中保留已完成回答、失敗另建 Run 重跑、429 重試不增加樣本、Worker 過期恢復、API 輸入驗證、同源寫入、SSE、CSV 公式跳脫、三種規則評分、供應商請求格式及異常回應。

## 尚未驗證 / 已知限制
- Docker 容器整組啟動與 PostgreSQL / Redis / Celery 的整合尚未實測，僅完成配置驗證。
- 未使用真實 API Key，未產生付費模型呼叫；供應商介面以 HTTP mock 驗證。
- 測試依賴發出兩個上游棄用警告（Starlette 的 httpx TestClient 與 AnyIO alias），不影響目前通過結果。
- 使用情境是本機私人單人；登入、多租戶、費用估算、跨 Run 回歸比較與安全基準引擎不在本版。

依賴重現：frontend/package-lock.json、backend/requirements.lock。業務資料與 .local-key 不進 Git。


# v0.2 驗證紀錄

日期：2026-09-23。Windows / Python 3.12 / SQLite，獨立 API 與 Worker，預覽 5175。

## 已通過
- `python -m pytest -q`：38 passed。保留 v0.1 15 項測試，新增連線、目錄、錯誤分類與 migration 測試。
- `npm run build`：TypeScript 與 Vite 正式建置成功。
- `python -m pip check`：依賴一致；對後端業務碼及新增測試執行 Ruff F 規則檢查成功。
- 本機 v0.1 SQLite 升級成功，建立一次 pre-v02 備份；原有 2 個 Demo、1 個 Run、20 筆結果與人工評分保留。
- 公開 OpenRouter `/models` GET（無金鑰、無推論）實測：454 筆清單可解析，430 筆支援固定文字輸入輸出。
- 瀏覽器隔離環境使用暫存 SQLite、虛構 QA Key 與模擬廠商回應；完成新增連線、驗證、同步、免費 / 名稱篩選、批次加入兩模型、試跑提示及成功回饋。
- 隔離 UI 建立一模型 × 10 題 Run，10 / 10 完成；展開路由資訊可見請求 / 回傳模型、provider、generation ID、金鑰版本與費用。這些數字是驗收模擬資料，不是真實模型評測。
- 停用連線後模型不可試跑；重新啟用、換成無效 QA Key、再驗證能顯示無效狀態，未暴露金鑰。瀏覽器未出現 JavaScript error / warning。
- 目錄畫面截圖已檢查，版面與價格 / 能力標示正常。

## 新增測試涵蓋
- 金鑰加密與 API / 驗證錯誤不外洩，固定 OpenRouter endpoint，metadata 僅 GET。
- 快取 TTL、強制同步、篩選與分頁 API、同步失敗保留快取、下架模型保留配置但不可新測。
- 自動 router / 非文字模型拒絕、同連線批次去重與併行匯入、跨連線獨立。
- 換 Key 待驗證、停用禁止呼叫、驗證途中換 Key 不誤蓋、手動模型仍可使用。
- 參數能力與輸出上限驗證、不可變快照、執行時新金鑰版本、實際路由 / 用量 / cost、JSON / CSV 匯出。
- 401 / 402 / 429 / 5xx、HTTP 200 內嵌錯誤、Retry-After 過長、in-flight budget、重試期間取消、逾時不重播、費用未知。
- 真正的 v0.1 無 Alembic stamp 檔案升級；模型 ID、不同比對金鑰、Run / Item / Review 內容保留，foreign_key_check、再次升級冪等及備份原 schema。

## 未驗證與限制
- 未提供真實 API Key，因此 /key 成功驗證、真實 chat completion / 計費均以 HTTP mock 或隔離 fixture 驗證，未進行付費呼叫。
- PostgreSQL migration 與完整 Docker / Redis / Celery runtime 尚未實測；此版不宣稱已通過。
- 仍有兩個上游 TestClient / AnyIO 棄用警告；測試結果正常。
- API / 前端無登入授權，維持 loopback；QA fixture 與暫存資料不放入正式使用者資料庫或 Git。
