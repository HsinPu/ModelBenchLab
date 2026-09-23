# ModelBenchLab

繁體中文 LLM 評估工作台：用同一份題庫比較多個模型的回答、品質與延遲。

## v0.1 功能
- OpenAI 相容模型 API、本機端點、加密 API Key、連線測試。
- 兩個不需金鑰的 Demo 模型與 10 題範例，可直接走完流程。
- 題庫 / Prompt 不可變版本；JSON、CSV 匯入與多輪對話。
- 背景執行、即時進度、取消、失敗重跑、設定快照。
- 完全比對、包含文字、JSON Schema、人工評分。
- 並排比較、失敗篩選、JSON / CSV 匯出。

Demo 模型使用固定答案和模擬延遲，不代表真實模型品質或效能。

## Windows 快速啟動（Python 3.12+、Node.js 22+）
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
cd frontend
npm ci
cd ..
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```
開啟 http://127.0.0.1:5173 。點「建立測試」，保留兩個 Demo 模型並開始，即可比較 20 個工作項目。
若 5173 被占用，可在啟動指令末尾加上 `-FrontendPort 5175`。
後端 API 文件：http://127.0.0.1:8000/docs 。
停止：`powershell -ExecutionPolicy Bypass -File scripts/stop-local.ps1`。
日誌位於 work/；資料庫與本機加密主金鑰位於 backend/modelbench.db、backend/.local-key，皆不進 Git。請一起備份，遺失金鑰後無法還原既有 API Key。

## 手動啟動 / macOS / Linux
安裝相同依賴並啟用虛擬環境，在 backend/ 分別執行 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` 與 `python -m app.execution`；frontend/ 執行 `npm run dev`。

## Docker Compose
複製 .env.example 為 .env，填入 POSTGRES_PASSWORD；產生 APP_ENCRYPTION_KEY：
```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose up --build -d
```
開啟 http://127.0.0.1:8080 。包含 PostgreSQL、Redis、API、Celery Worker、Beat 與前端。
Docker 內連本機模型服務時，Windows/macOS 的端點通常改用 `http://host.docker.internal:11434/v1`。
本版無登入功能，只限可信任的本機/私人使用，預設不暴露公網。

## 匯入格式
CSV：title,question,kind,expected（見 examples/basic.csv）。kind 可用 exact、contains、manual；JSON Schema 或多輪訊息使用 JSON。
```json
[{"title":"算術","messages":[{"role":"user","content":"2 + 2"}],"rule":{"kind":"exact","expected":"4"},"tags":["math"]}]
```

## 驗證
```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
cd ../frontend
npm run build
```

## 邊界
v0.1 尚無帳號權限、串流、LLM Judge、跨 Run 回歸比較、費用估算、MLCommons 整合、資料庫 migration。真實模型的 temperature/max_tokens 支援依供應商而定；目前使用非串流 chat/completions 文字回應。
本專案獨立開發，未複製 MLCommons ModelBench 程式碼，亦無官方關聯。
詳見 docs/architecture.md、docs/verification.md、AGENTS.md。
