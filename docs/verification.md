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
