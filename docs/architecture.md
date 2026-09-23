# ModelBenchLab v0.1 架構

React + TypeScript → FastAPI → SQLAlchemy → SQLite（本機）/ PostgreSQL（Compose）。
API 建立 Run 與 RunItem，背景 Worker 呼叫模型 Adapter，再透過 Evaluator 評分。
前端透過 SSE 接收進度，重連後重新讀取資料庫狀態。

## 實作決策

- 一個 repository、模組化單體，API 和 Worker 分別運行。
- 本機以資料庫輪詢佇列執行，預設一次一題，不依賴 Docker。
- Compose 使用 Redis + Celery worker（併發 2），Beat 每 30 秒重新派送待執行項目。
- SQL 原子條件更新 claim item，重複派送不重複計入結果。
- 每次測試保存題庫、Prompt、模型配置和參數快照；不保存解密金鑰。
- 題庫和 Prompt 採 append-only 版本，編輯即另存新資料。
- 一個 item 對應題目 × 模型 × 重複次數；每次請求重試獨立保存在 attempts。
- 模型 key 加密保存，主金鑰在環境變數；本機開發使用 gitignored .local-key。
- 取消會停止待執行項目；已發出的 API 請求可能仍完成並計費。
- 429、5xx、連線及逾時錯誤最多重試兩次。上游不保證 exactly-once 計費。
- Worker 工作 12 分鐘未完成會標記失敗，不自動重播不確定請求；使用者可重跑失敗項目至新 Run。
- 自動評分通過率只包含有 true/false 結果的成功回答；人工評分與服務失敗另外記錄。
- PostgreSQL/SQLite JSON 欄位保存版本內容、快照、結果、評分與 attempts；小型 MVP 暫不拆成完整明細表。

## 範圍邊界

第一版：本機/私人單人使用、OpenAI 相容文字介面、多輪訊息、自動 exact/contains/JSON Schema 評分、人工評分、JSON/CSV 匯入匯出、取消與重跑。

未納入：登入、多租戶、模型串流、供應商專屬 Adapter、Prompt 變數替換、正則評分、費用計算、每供應商限流、跨 Run 基準比較、LLM Judge、MLCommons ModelBench 整合。

Schema 初始化採 create_all，只適用新資料庫。第二版修改 schema 前需導入 Alembic；不可假設 create_all 會升級既有資料表。
API 支援自訂本機 URL，因此不適合直接暴露公網；Compose 與本機腳本僅綁定 loopback。多人部署前加入認證、權限、端點存取政策。

## API

GET/POST /api/models、/api/datasets、/api/prompts、/api/runs。
POST /api/models/{id}/test。
GET /api/runs/{id}、/events、/export?format=json|csv。
POST /api/runs/{id}/cancel、/retry。
POST /api/items/{id}/review、/evaluate。
GET /api/health。OpenAPI: /docs。
