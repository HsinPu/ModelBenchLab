# ModelBenchLab v0.2 架構

React + TypeScript → FastAPI → SQLAlchemy → SQLite（本機）/ PostgreSQL（Compose）。API 建立不可變 Run 快照與工作項目，獨立 Worker 呼叫模型，再用 Evaluator 評分；前端以 SSE 更新進度。

## 模組

| 模組 | 職責 |
| --- | --- |
| frontend/src/features/models | 我的模型、廠商連線、模型目錄與試跑介面 |
| backend/app/connections.py | 連線生命週期、金鑰輪替、目錄快取、批次或手動加入模型、模型可用性 |
| backend/app/provider_types.py | 可用服務類型、位址規則、金鑰需求、目錄與驗證能力；新增廠商的登錄入口 |
| backend/app/openrouter.py | OpenRouter metadata GET、目錄正規化、可重試錯誤分類 |
| backend/app/tmmluplus.py | 固定官方版本與科目白名單、限量下載或本機 CSV 轉換、可重現抽樣 |
| backend/app/coding_benchmarks.py | HumanEval／HumanEval+ 白名單檔案、固定 SHA、限量資料解析及可重現抽樣 |
| backend/app/coding.py + coding_runner/ | Docker-only Python 評分、runtime 快照、取消、固定結果碼；無宿主程式執行 fallback |
| backend/app/providers.py | Demo / OpenAI 相容 / OpenRouter chat completion 與用量解析 |
| backend/app/execution.py | 工作 claim、取消、重試、實際金鑰版本與結果保存 |
| backend/app/db.py + migrations | SQLAlchemy 結構、Alembic migration、SQLite 升級前備份 |

## 資料關係

- ProviderConnection 1 → N ModelConfig；一組加密金鑰對應多個模型，啟用與驗證狀態由連線管理。
- ModelConfig 刪除採歸檔（deleted_at + enabled=false），因此既有 Run 的模型 ID、快照、Item 與 Review 不受影響。歸檔模型不出現在新測試選擇中；使用同一上游模型重新加入時建立新 ID。
- 目前服務類型為 OpenRouter 與自訂 OpenAI 相容服務。前者由 metadata 驗證並同步目錄；後者保存自訂 Base URL，模型 ID 手動加入，透過付費可能的短試跑確認連通。兩者可各建多組連線。
- ProviderConnection 1 → N CatalogModel；連線 + model ID 唯一，保存價格、Context、能力、可用狀態、同步時間。
- Dataset / Prompt 為不可變版本。Run 保存題庫、Prompt、模型配置（含可選思考程度與每模型輸出 Token 上限）、路由、建立時金鑰版本與參數快照，不保存金鑰。若 Run 未指定共同 `max_tokens`，每個 Item 使用各自模型快照的上限；歷史 Run 的明確 `max_tokens` 繼續照舊執行。
- Dataset 刪除使用 `deleted_at` 歸檔，不硬刪題目與歷史資料；列表與新 Run 排除歸檔版本，bundle 內所有 Dataset 在同一交易一起歸檔。已建立 Run 的快照與 Item 獨立於題庫列表，可繼續執行與檢視。
- Run 刪除使用 `deleted_at` 歸檔，batch 內所有 Run 同一交易處理。Run 或 Item 還在排隊、執行或取消中時拒絕歸檔，避免背景工作失去可見紀錄；歸檔後列表、詳情、匯出、重跑與 Item 評分入口排除它，Run 快照、Item 與 Review 仍留存資料庫。
- TMMLU+ 匯入先回傳預覽，使用者確認後透過既有 Dataset API 保存；Case 來源欄位保留資料集、版本、科目、分割、列號、原始連結與匯入方式，隨 Run 快照保存，不需新增資料表。
- 題庫匯入介面先選來源，再選已支援的資料集。Hugging Face 題庫以明確清單登錄，現階段只有 TMMLU+，可選官方最新或固定 v1.1；本機 JSON / CSV 使用同一入口，但先載入題庫編輯器供檢查。一般 CSV 題目標記 `local_csv` 與原始列號，不冒用官方來源。
- TMMLU+ 最新版本入口每次從官方 metadata 解析 `main` 的 SHA，從同一版本的 `_val.csv` 與 `_test.csv` 檔案交集產生科目清單；預覽請求指定不可變 SHA，後端再驗證該 SHA 的官方科目與檔案，整次全科匯入不混用版本。本機 TMMLU+ CSV 僅在固定 v1.1 模式提供，並標記 `uploaded_csv`；不將其內容冒充為已驗證的最新版本。
- TMMLU+ 可預覽單科或當前版本全部科目的固定抽樣／完整分割。超過 1000 題後，一次交易保存為有共同 bundle ID 的多個 Dataset，每批最多 1000 題。清單僅回傳批次題數，不反覆傳送整組題目。
- 整組題庫可一次建立多個 Run，共用 batch ID；依所選模型與重複次數將每批限制在 5000 工作項目，整組限制 50000。所有 Run 和 Item 在同一交易建立，排程器處理餘下佇列工作。費用確認在 UI 的明確送出步驟。
- Run 1 → N Item；每個 item 對應題目 × 模型 × 重複次數，重試保存於 attempts，不增加樣本。
- Item 結果保存回答、規則評分、延遲、token、cost、回傳模型 / provider / generation ID、實際金鑰版本。無文字回應若帶有 `usage.cost`，失敗 attempt 也只保存安全的費用欄位。Run 清單、詳情與 SSE 從 Item 結果及 attempt 以 Decimal 即時計算「已回報費用」，不改寫歷史快照，也不以目錄價格推算扣款；未知與可能重試計費分開提示。HumanReview 另存人工評分，不混入自動通過率。
- OpenRouter 目錄只以文字輸入與文字輸出能力決定能否加入。Run 快照保存目錄參數能力；請求略過未宣告支援的 `temperature` / `max_tokens`。動態路由 ID 不強加固定 provider policy，逐題保存回傳模型；其排行榜列是路由策略合計，不代表單一模型。
- 總覽自動選用 `/api/runs` 最新 Run 的不可變題庫版本，從 `/api/runs/{id}/dataset-ranking` 比較同版本各次測試的模型。候選 Run 必須涵蓋題庫全部題目；分批題庫驗證各 part 的題目集合後合併，同模型只取最近一次涵蓋完整題組的測試，失敗重跑不當成獨立完整測試。僅 completed 且 `evaluation.passed` 為布林值的 Item 納入通過率分母，未評分、失敗與取消另行呈現；執行中與已取消的部分成績不列正式名次。舊 `/api/runs/{id}/ranking` 保留單場測試彙總，其他 Run 從測試紀錄進入結果頁。

## 執行決策

- 本機採 SQLite 輪詢佇列、預設一次一題；Compose 採 Redis + Celery（併發 2），Beat 每 30 秒重新派送待執行項目。
- SQL 條件更新 claim，重複投遞不會再次執行已接手的 item。上游無 exactly-once 計費保證。
- 每次請求前檢查 Run 取消狀態、模型 / 連線啟用與金鑰驗證；金鑰輪替後使用最新版本，歷史快照不變。
- 429 / 5xx / 明確暫時性 402 最多重試兩次，尊重 Retry-After；超過 30 秒改為失敗，避免提前重送。逾時與傳輸中斷不自動重播。
- 一般取消停止待執行項目與重試，已送出的回應可保存。`POST /api/runs/{id}/force-cancel` 則在同一交易將整個 batch 的活動 Run 和未完成 Item 標為取消；Worker 使用 async HTTP 請求並輪詢取消狀態，中斷本機等待。Item 保存與 Run 收尾均採條件更新，防止晚到回應或收尾程序覆寫強制取消。斷開本機連線不能保證上游停止處理或不計費。30 分鐘未完成的工作標為失敗，需要手動確認後重跑至新 Run；網路等待預設 600 秒、可設 5–600 秒，與整題總耗時不同。
- 同一連線同步 / 匯入透過寫入鎖序列化，批次加入先全數驗證，避免半套結果與並行重複。
- metadata HTTP 請求不持有資料庫寫入鎖；回寫時比較金鑰版本並鎖定，避免慢請求覆蓋新金鑰狀態。
- 上游錯誤使用固定可讀訊息，不保存原始 body / header；輸入驗證回應移除 input / context，避免回傳 API Key。
- 無文字回應與網路逾時分開分類：前者依上游 `finish_reason`、後者依 HTTPX 逾時例外；只保存允許清單中的狀態、實際模型、Token 用量、等待類型與耗時診斷，不記錄原始回應。HTTPX 的等待逾時不等於整題總耗時硬上限。
- 每個模型的思考程度可留空採模型預設，或手動選 `low` / `medium` / `high` / `xhigh` / `max` / `ultra`。OpenRouter 使用 `reasoning.effort`，自訂相容服務使用 `reasoning_effort`；不做隱式轉換或 fallback。上游拒絕參數時提示可能不支援所選程度。

## Schema 升級

Alembic `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007` 同時支援空資料庫及 v0.1 無 stamp 資料庫。啟動時 SQLite 使用 BEGIN IMMEDIATE，PostgreSQL 使用 advisory transaction lock，避免多程序同時升級。SQLite 變更前建立一致性備份；PostgreSQL 需由管理者備份。詳見 [OpenRouter 操作與回復](openrouter.md)。

## API

- GET / POST `/api/models`、`/api/datasets`、`/api/prompts`、`/api/runs`
- DELETE `/api/datasets/{id}` 歸檔題庫版本；若版本屬於 bundle，整組批次同時歸檔。
- DELETE `/api/runs/{id}` 歸檔已結束的測試紀錄；若 Run 屬於 batch，整批一起歸檔。
- 測試結果前端將 Item 依題目與重複次數分組，只渲染目前頁面的 20 題；回答預設收起並在使用者展開該題時建立。API 詳情仍回傳完整快照及 Item，供匯出、評分與即時更新使用。
- 逐題篩選將有回答但規則評分未通過（`evaluation.passed=false`）與請求／執行失敗（Item `status=failed`）分開；多模型同題只要任一模型符合條件，該題便會顯示，展開後仍可對照所有模型回答。
- GET `/api/benchmarks/tmmluplus` 列出固定 v1.1 科目；GET `/api/benchmarks/tmmluplus/latest` 即時解析官方 main commit 與科目；POST `/api/benchmarks/tmmluplus/preview` 以 v1.1 或指定 commit SHA 下載分割並回傳題目預覽，固定 v1.1 也可解析使用者提供的 CSV。
- GET `/api/providers` 列出服務類型及可用能力；POST `/api/connections/{id}/models/manual` 在自訂服務連線下加入模型
- PATCH `/api/models/{id}` 啟停或修改思考程度；DELETE `/api/models/{id}` 歸檔；POST `/api/models/{id}/test` 試跑
- GET / POST `/api/connections`；PATCH `/api/connections/{id}` 更名、金鑰、啟停
- POST `/api/connections/{id}/verify`；POST `/sync?force=true|false`
- GET `/api/connections/{id}/catalog?q=&author=&free_only=&text_only=&capability=&offset=&limit=`
- POST `/api/connections/{id}/models` 批次加入
- GET `/api/runs/{id}`、`/events`、`/export?format=json|csv`
- POST `/api/runs/{id}/cancel`、`/retry`；POST `/api/items/{id}/review`、`/evaluate`
- GET `/api/health`；OpenAPI `/docs`

## 邊界

BFCL V3 Python 單輪工具調用以原生 tools/tool_calls 執行，固定來源與 Python AST 比較規則；不執行工具函式。Run v4 在既有 JSON 保存 BFCL 規格、SHA 與評分 runtime；回答保存後才評分，重評沿用原回答，同 runtime 才合併排名。詳見 [bfcl-benchmarks.md](bfcl-benchmarks.md)。此成績不是完整官方排行榜或長時間 Agent 測試。

題庫排行榜由 Dataset.bundle_id 決定完整範圍，不依參考 Run 是否帶 batch_id 縮小題組；部分批次不取代完整成績。BFCL adapter 僅轉換 Schema 子節點，保留 enum/default 等資料常值；候選数值在比較過程溢位判為答錯，其他評分器例外維持獨立失敗狀態。

Python Coding 題庫已接入 HumanEval／HumanEval+，由 Docker-only 評分器執行固定版本的 HF 測試；模型生成結果先保存，評分與重新生成分離。Coding Run 使用 v3 JSON 快照，資料表結構未變；同題庫、runtime 與 code timeout 才合併排名。詳見 [coding-benchmarks.md](coding-benchmarks.md)。此功能尚不支援 Compose runtime、跨套件重評或官方 EvalPlus 完整 harness。

本機私人單人使用，支援固定模型與動態路由的非串流文字評估。圖片、音訊、影片輸出與 embedding 尚無對應題型和評分。登入、多租戶、工具實際執行、模型串流、Prompt 變數、服務商鎖定、每廠商限流排程、費用預算控制、跨 Run 回歸比較、LLM Judge 與 MLCommons 整合尚未納入。

允許自訂本機端點，因此不能直接暴露公網；本機腳本與 Compose 綁定 loopback。多人部署前須加入認證、權限、端點存取政策。
