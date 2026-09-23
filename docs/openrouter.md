# OpenRouter 連線與模型目錄

## 操作流程

1. 進入「模型管理 → 廠商連線 → 新增 OpenRouter 連線」，輸入連線名稱與自己的 API Key。
2. 點「驗證金鑰」。後端只呼叫 `GET https://openrouter.ai/api/v1/key`，不產生模型推論。
3. 點「瀏覽模型」同步清單，或進入「模型目錄」點「更新目錄」。一般同步使用 15 分鐘快取；更新目錄會強制同步。
4. 搜尋模型名稱 / ID，依模型作者、免費、文字輸入輸出與能力篩選，再勾選批次加入。每次最多 100 個；同一連線重複加入會略過。
5. 在「我的模型」點「試跑模型」可發送一筆短請求。畫面會先說明可能計費，試跑不加入正式 Run。
6. 點「建立測試」，選擇新加入的模型、題庫與 Prompt。結果可查看請求模型、回傳模型、服務商、generation ID、實際使用的金鑰版本與費用；JSON / CSV 匯出也保留這些資訊。

模型目錄中的「工具、推理、JSON」為廠商宣告的能力標籤，此版測試仍只使用非串流文字介面，不會執行工具。自動 router、非文字輸入輸出模型不可加入。缺少本版所用 `temperature` / `max_tokens` 的模型會提示不支援，建立測試時明確拒絕，不會悄悄忽略參數。

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
- 顯示上游 `usage.cost`（USD 計價 credits）；缺漏一律為未知，不拿目錄單價推估實際扣款。目錄顯示的輸入 / 輸出價格以每百萬 tokens 換算，其他費目以廠商為準。
- 429、5xx 及明確的暫時性 in-flight budget 402 最多重試兩次。優先遵守 `Retry-After`；沒有時採 1 / 2 秒退避。等待期間仍可取消。
- `Retry-After` 超過 30 秒時保留失敗，交由使用者稍後重跑，不提前重送。
- 一般 402 不重試，提示檢查帳戶或金鑰額度。逾時 / 傳輸中斷可能已計費，不自動重試；確認後可把失敗項目重跑到新 Run。
- 同步失敗保留上一份目錄與時間；成功同步後消失的模型標為下架，保留已加入配置與歷史資料。

## 升級與回復

啟動 API / Worker 時執行 Alembic，使用資料庫鎖避免同時升級。`0001` 採納 v0.1 表結構或建立新資料庫；`0002` 新增連線與模型目錄。

升級前先停止舊 API / Worker。本機 SQLite 在變更 schema 前會自動建立 `backend/modelbench.db.pre-v02-<UTC時間>.bak`，包含已提交的 WAL 內容。備份檔已忽略，不進 Git。仍需自行備份 `.local-key` 或保存 `APP_ENCRYPTION_KEY`；資料庫備份不能取代主金鑰備份。PostgreSQL 請先以 `pg_dump` 自行備份。

舊有非 Demo 模型各自遷移成獨立連線，原加密金鑰移入連線表；即使 endpoint 相同也不合併。模型 ID、Run 快照、回答與人工評分不變。Demo 保留原行為。

此版不提供破壞性的 downgrade。要回復時先停止服務，保存目前資料庫，再以備份恢復 SQLite（確認舊 WAL / SHM 不混用）並切回相應版本程式。先在隔離環境測試恢復。

## 官方參考

- [模型目錄](https://openrouter.ai/docs/api/api-reference/models/get-models)
- [額度與限流](https://openrouter.ai/docs/api_reference/limits)
- [服務商路由](https://openrouter.ai/docs/guides/routing/provider-selection)
- [用量與費用](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
