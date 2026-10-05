# OpenRouter 連線與模型目錄

## 操作流程

1. 進入「模型管理 → 廠商連線 → 新增廠商連線」，選擇 OpenRouter，輸入連線名稱與自己的 API Key。
2. 點「驗證金鑰」。後端只呼叫 `GET https://openrouter.ai/api/v1/key`，不產生模型推論。
3. 點「加入模型」瀏覽目錄；一般同步使用 15 分鐘快取，「更新目錄」會強制同步。
4. 搜尋模型名稱 / ID，依模型作者、免費、文字輸入輸出與能力篩選，再勾選批次加入。每次最多 100 個；同一連線重複加入會略過。加入前可手動選擇思考程度及輸出 Token 上限，批次套用到這次新加入的模型。
5. 在「我的模型」點「試跑模型」可發送一筆短請求。畫面會先說明可能計費，試跑不加入正式 Run。
6. 點「建立測試」，選擇新加入的模型、題庫與 Prompt。結果可查看請求模型、回傳模型、服務商、generation ID、實際使用的金鑰版本與費用；JSON / CSV 匯出也保留這些資訊。

模型目錄中的「工具、推理、JSON」為廠商宣告的能力標籤，此版測試仍只使用非串流文字介面，不會執行工具。可接收文字並回傳文字的模型皆可加入，包括 Auto Router 和動態別名；只能輸出非文字內容的模型需另有題型與評分才能測。缺少 `temperature` / `max_tokens` 能力的模型仍可測文字題，請求會略過未宣告支援的欄位，加入與建立測試畫面會提示。

Auto Router 由 OpenRouter 逐題選擇實際模型，不能把它的合計通過率當成某一固定模型的成績。Run 快照保存請求的 router ID，結果保留上游回傳的實際模型與費用；動態路由不套用固定 provider policy，目錄價格不能代表最終費用。

思考程度可選模型預設、`low`、`medium`、`high`、`xhigh`、`max`、`ultra`；後六種在 OpenRouter 請求中原樣送為 `reasoning.effort`。這是手動設定，系統不預先假定每個模型支援所有程度。若 OpenRouter 拒絕請求，錯誤會提示檢查所選程度及其他參數。`ultra` 不在目前 OpenRouter 通用文件列出的 effort 值中，沒有保證能使用。既有模型可在詳情中修改；歷史 Run 保留建立時的程度設定。

新增模型的輸出 Token 上限預設 128,000，可在加入模型時或模型詳情設定；既有模型與歷史 Run 保持原設定。目錄宣告支援 `max_tokens` 時，試跑照模型設定送出，正式測試可選擇按各模型值或共同覆寫；未宣告支援時不送此欄位，實際上限由上游決定。Run 快照保存建立時設定。目錄若提供 `max_completion_tokens` 且支援 `max_tokens`，低於將送出的上限時建立測試或試跑會明確拒絕並顯示目錄上限。高上限可能增加費用，但不代表每次都會用滿；動態路由的實際模型也可能有較低限制。

## 金鑰與停用

- API Key 由後端 Fernet 加密保存，前端只收到 `has_key`，不回填原值；請勿在對話、文件或 Git 貼入真實金鑰。
- 連線的「編輯 / 更換金鑰」可更名、輪替金鑰。留白保留原金鑰；更換後 OpenRouter 連線須重新驗證。
- 所屬模型共用連線金鑰。未發送的工作會在每次嘗試前讀取最新金鑰並檢查啟用與驗證狀態。Run 快照保留建立時版本，結果另外記錄實際版本。
- 停用模型或連線會阻止後續新請求，不修改已完成的歷史結果。已發出的請求可能完成並計費。
- 401 / 403 將連線標示為無效，直到使用者重新驗證；更換金鑰時不會被舊請求的失敗結果誤蓋。
- 畫面上的上限、剩餘額度與用量來自 `/key`，是金鑰層級資料，**不是帳戶餘額**。驗證時更新，非持續即時查詢。

## 路由、費用與重試

- 固定 OpenRouter API 位址，不接受使用者改寫 URL。請求只傳單一明確模型 ID，不使用 `models` 自動 fallback。
- `provider.allow_fallbacks=false`、`provider.require_parameters=true` 保存於模型及 Run 快照。不同測試仍可能被 OpenRouter 分配到不同服務商；此版沒有服務商鎖定功能，以回應 metadata 作追溯。
- 顯示上游 `usage.cost`（USD 計價 credits）；測試紀錄逐題、整場與各模型小計使用上游已回報費用，執行中隨完成項目更新。已回應但無文字的失敗 attempt 若有 `usage.cost` 也納入；缺漏與可能已計費的失敗請求標示費用未明，不拿目錄單價推估實際扣款。目錄顯示的輸入 / 輸出價格以每百萬 tokens 換算，其他費目以廠商為準。
- 429、5xx 及明確的暫時性 in-flight budget 402 最多重試兩次。優先遵守 `Retry-After`；沒有時採 1 / 2 秒退避。等待期間仍可取消。
- `Retry-After` 超過 30 秒時保留失敗，交由使用者稍後重跑，不提前重送。
- 一般 402 不重試，提示檢查帳戶或金鑰額度。逾時 / 傳輸中斷可能已計費，不自動重試；確認後可把失敗項目重跑到新 Run。
- 試跑與新測試的網路等待預設為 600 秒，可各自設定 5–600 秒。`timeout` 是 HTTPX 的連線、讀取、寫入與連線池等待限制，不是請求總耗時硬上限。上游若回傳成功 HTTP 狀態、空白文字與 `finish_reason=length`，分類為無文字輸出，不是本工具的網路逾時；不能僅憑此訊號斷言推理 Token 用盡。後續正式測試失敗紀錄保留允許清單中的 HTTP 狀態、結束原因、實際模型、Token 用量與耗時，便於區分，並不保存原始回應或推理文字。
- 同步失敗保留上一份目錄與時間；成功同步後消失的模型標為下架，保留已加入配置與歷史資料。

## 升級與回復

啟動 API / Worker 時執行 Alembic，使用資料庫鎖避免同時升級。`0001` 採納 v0.1 表結構或建立新資料庫；`0002` 新增連線與模型目錄；`0003` 加入模型歸檔；`0004` 加入可選思考程度；`0005` 加入分批題庫與測試識別。

升級前先停止舊 API / Worker。本機 SQLite 在變更 schema 前會自動建立 `backend/modelbench.db.pre-v02-<UTC時間>.bak`，包含已提交的 WAL 內容。備份檔已忽略，不進 Git。仍需自行備份 `.local-key` 或保存 `APP_ENCRYPTION_KEY`；資料庫備份不能取代主金鑰備份。PostgreSQL 請先以 `pg_dump` 自行備份。

舊有非 Demo 模型各自遷移成獨立連線，原加密金鑰移入連線表；即使 endpoint 相同也不合併。模型 ID、Run 快照、回答與人工評分不變。Demo 保留原行為。

此版不提供破壞性的 downgrade。要回復時先停止服務，保存目前資料庫，再以備份恢復 SQLite（確認舊 WAL / SHM 不混用）並切回相應版本程式。先在隔離環境測試恢復。

## 官方參考

- [模型目錄](https://openrouter.ai/docs/api/api-reference/models/get-models)
- [額度與限流](https://openrouter.ai/docs/api_reference/limits)
- [服務商路由](https://openrouter.ai/docs/guides/routing/provider-selection)
- [用量與費用](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
- [思考程度與 token 預算](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
