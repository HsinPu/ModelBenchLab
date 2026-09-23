# ModelBenchLab v0.2 架構

React + TypeScript → FastAPI → SQLAlchemy → SQLite（本機）/ PostgreSQL（Compose）。API 建立不可變 Run 快照與工作項目，獨立 Worker 呼叫模型，再用 Evaluator 評分；前端以 SSE 更新進度。

## 模組

| 模組 | 職責 |
| --- | --- |
| frontend/src/features/models | 我的模型、廠商連線、模型目錄與試跑介面 |
| backend/app/connections.py | 連線生命週期、金鑰輪替、目錄快取、批次加入、模型可用性 |
| backend/app/openrouter.py | OpenRouter metadata GET、目錄正規化、可重試錯誤分類 |
| backend/app/providers.py | Demo / OpenAI 相容 / OpenRouter chat completion 與用量解析 |
| backend/app/execution.py | 工作 claim、取消、重試、實際金鑰版本與結果保存 |
| backend/app/db.py + migrations | SQLAlchemy 結構、Alembic migration、SQLite 升級前備份 |

## 資料關係

- ProviderConnection 1 → N ModelConfig；一組加密金鑰對應多個模型，啟用與驗證狀態由連線管理。
- ProviderConnection 1 → N CatalogModel；連線 + model ID 唯一，保存價格、Context、能力、可用狀態、同步時間。
- Dataset / Prompt 為不可變版本。Run 保存題庫、Prompt、模型配置、路由、建立時金鑰版本與參數快照，不保存金鑰。
- Run 1 → N Item；每個 item 對應題目 × 模型 × 重複次數，重試保存於 attempts，不增加樣本。
- Item 結果保存回答、規則評分、延遲、token、cost、回傳模型 / provider / generation ID、實際金鑰版本。HumanReview 另存人工評分，不混入自動通過率。

## 執行決策

- 本機採 SQLite 輪詢佇列、預設一次一題；Compose 採 Redis + Celery（併發 2），Beat 每 30 秒重新派送待執行項目。
- SQL 條件更新 claim，重複投遞不會再次執行已接手的 item。上游無 exactly-once 計費保證。
- 每次請求前檢查 Run 取消狀態、模型 / 連線啟用與金鑰驗證；金鑰輪替後使用最新版本，歷史快照不變。
- 429 / 5xx / 明確暫時性 402 最多重試兩次，尊重 Retry-After；超過 30 秒改為失敗，避免提前重送。逾時與傳輸中斷不自動重播。
- 取消停止待執行項目與重試；已送出的回應可保存。12 分鐘未完成的工作標為失敗，需要手動確認後重跑至新 Run。
- 同一連線同步 / 匯入透過寫入鎖序列化，批次加入先全數驗證，避免半套結果與並行重複。
- metadata HTTP 請求不持有資料庫寫入鎖；回寫時比較金鑰版本並鎖定，避免慢請求覆蓋新金鑰狀態。
- 上游錯誤使用固定可讀訊息，不保存原始 body / header；輸入驗證回應移除 input / context，避免回傳 API Key。

## Schema 升級

Alembic `0001 → 0002` 同時支援空資料庫及 v0.1 無 stamp 資料庫。啟動時 SQLite 使用 BEGIN IMMEDIATE，PostgreSQL 使用 advisory transaction lock，避免多程序同時升級。SQLite 變更前建立一致性備份；PostgreSQL 需由管理者備份。詳見 [OpenRouter 操作與回復](openrouter.md)。

## API

- GET / POST `/api/models`、`/api/datasets`、`/api/prompts`、`/api/runs`
- PATCH `/api/models/{id}` 啟停；POST `/api/models/{id}/test` 試跑
- GET / POST `/api/connections`；PATCH `/api/connections/{id}` 更名、金鑰、啟停
- POST `/api/connections/{id}/verify`；POST `/sync?force=true|false`
- GET `/api/connections/{id}/catalog?q=&author=&free_only=&text_only=&capability=&offset=&limit=`
- POST `/api/connections/{id}/models` 批次加入
- GET `/api/runs/{id}`、`/events`、`/export?format=json|csv`
- POST `/api/runs/{id}/cancel`、`/retry`；POST `/api/items/{id}/review`、`/evaluate`
- GET `/api/health`；OpenAPI `/docs`

## 邊界

本機私人單人使用，支援固定模型的非串流文字評估。登入、多租戶、工具實際執行、模型串流、Prompt 變數、服務商鎖定、每廠商限流排程、費用預算控制、跨 Run 回歸比較、LLM Judge 與 MLCommons 整合尚未納入。

允許自訂本機端點，因此不能直接暴露公網；本機腳本與 Compose 綁定 loopback。多人部署前須加入認證、權限、端點存取政策。
