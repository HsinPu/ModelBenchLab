# ModelBenchLab — Agent 工作規範

## 專案目標
建立前後端分離的 LLM 評估工作台。先完成可追溯題庫/Prompt、背景測試、規則評分與結果比較；後續再接安全基準測試引擎。

## 結構
- frontend/: React + TypeScript + Vite；繁體中文介面，色系為深綠、米白、淺草綠。
- backend/app/: FastAPI、SQLAlchemy、provider/evaluator、背景執行。
- backend/tests/: 隔離暫存資料庫的 pytest，不使用真實 API 金鑰。
- scripts/: Windows 本機啟停；所有背景啟動使用隱藏視窗。
- docs/architecture.md: 設計決策與已知限制。

## 必須保持的行為
1. 題庫/Prompt 另存新版本，Run 保存不可變設定快照；不可讓歷史測試受後續編輯影響。
2. API Key 不回傳前端、不寫入日誌、快照、測試、文件或 Git；只保存加密值。
3. Worker 使用條件更新 claim；重複投遞不可重複計分。
4. 回答不合格、API 失敗、待人工評分分開顯示；分母不能混用。
5. 重試和重複抽樣必須分開，取消後不再發出新模型請求。
6. 示範模型須標示為模擬，不把它的耗時或回答當真實模型基準。
7. 保持 loopback 部署，尚無登入授權，不能直接改為公網服務。
8. 新增 schema 變更先導入 migration，禁止用 create_all 假裝升級資料表。

## 開發與驗證
在 repository 根目錄：
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
cd frontend
npm ci
npm run build
cd ../backend
..\.venv\Scripts\python.exe -m pytest -q
```
在根目錄 `powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1` 啟動；`scripts/stop-local.ps1` 停止。
使用示範題庫與兩個 Demo 模型驗證完整 UI：建立測試 → 完成 → 比較 → 人工評分 → 匯出。

## 完成工作與提交
- 記錄具體測試結果及未驗證的環境；不要聲稱真實供應商或 Docker 通過，除非實際驗證。
- 更新 README、docs 及本檔中受改動影響的部分。
- Commit 前檢查 git diff --check、git status、測試結果，確保 .env、.local-key、資料庫和 logs 不進版控。
- 不自動 push；只有使用者授權時才推送。
- 第一版採精簡表結構；不要宣稱已實作 docs 中列出的下一階段功能。

## v0.1 完成紀錄（2026-09-22）
- 完成上述第一版核心流程，15 項後端測試通過；前端 build、pip check、Compose config 通過。
- 瀏覽器驗收完成 10 題 × 2 Demo 模型的 20 筆測試與人工評分。
- 預覽使用 5175（5173 已占用）；啟動腳本支援 -FrontendPort。
- 驗證細節及未驗證事項記於 docs/verification.md。
- 後續優先事項：模型配置編輯與金鑰輪替、模組拆分、Alembic、真實供應商測試，再加入登入與回歸比較。
