# ModelBenchLab

繁體中文 LLM 評估工作台：用同一份題庫比較多個模型的回答、品質與延遲。

## v0.2 功能
- OpenRouter 廠商連線、加密 API Key、驗證與輪替、共用金鑰及啟停。
- 模型目錄同步快取、搜尋 / 能力 / 免費篩選、分頁與批次加入。
- 模型詳情可刪除模型：從管理清單移除並停用，歷史測試與評分保留；執行中或排隊中的測試會阻止刪除。
- 保留手動 OpenAI 相容 API 與本機模型端點，試跑前提示可能費用。
- 結果記錄回傳模型、服務商、generation ID、token 與實際費用；缺漏資料顯示未知。
- Alembic 升級既有資料庫，SQLite 升級前自動備份。
- 兩個不需金鑰的 Demo 模型與 10 題範例，可直接走完流程。
- 題庫 / Prompt 不可變版本；JSON、CSV 匯入與多輪對話。
- 題庫卡片可刪除單一題庫或整組分批題庫；已建立的測試紀錄與結果保留。
- 測試紀錄列表與結果頁可刪除已結束的測試；同批次整組移除，執行中的測試須先取消。
- 題庫匯入先選 Hugging Face 或本機檔案；Hugging Face 目前支援 TMMLU+ 官方最新版本與固定 v1.1，依科目與分割匯入並保留來源資訊與固定抽樣。
- 背景執行、即時進度、取消、失敗重跑、設定快照。
- 完全比對、包含文字、選擇題答案、JSON Schema、人工評分。
- 並排比較、失敗篩選、JSON / CSV 匯出。
- 評估總覽顯示模型規則通過率柱狀排行榜，可切換測試；整批測試合併計算，執行中與已取消結果會明確標示。

Demo 模型使用固定答案和模擬延遲，不代表真實模型品質或效能。

排行榜只比較同一場測試（或同一組分批測試）中的模型，依有規則自動評分的回答計算通過率；人工評分、API 失敗及取消的題目不進分母。圖上同時顯示通過／已評分、已回答／總題數，避免把不同題庫或尚未完成的回答混算。

總覽集中顯示摘要統計與排行榜；完整測試清單請從左側「測試紀錄」檢視。

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

## 廠商連線
進入「模型管理 → 我的模型 → 加入模型」，選擇現有連線或在流程中建立新連線。若要編輯或停用連線，進入「廠商連線」並點「管理」。目前支援 OpenRouter，以及自訂 OpenAI 相容服務（例如本機模型伺服器）。

OpenRouter：輸入 API Key，保存連線後以 metadata 驗證，再從目錄搜尋、篩選及批次加入可回答文字題目的模型，包含 Auto Router；勾選項目在換頁或篩選後會保留。若目錄未宣告支援 Temperature 或 max_tokens，請求會略過該欄位並在介面提示。自訂服務：填寫 API Base URL，視需要輸入 API Key；保存後在同一連線下手動加入多個模型，再從「我的模型」試跑。服務類型會決定表單欄位與可用功能，後續可加入更多廠商。

加入模型時可選「模型預設」或手動指定 `low`、`medium`、`high`、`xhigh`、`max`、`ultra` 思考程度；批次加入會將同一設定套用到本次新加入的模型。既有模型可在「我的模型 → 詳情」修改。試跑與新建立的正式測試都使用模型設定，正式測試保存當時的值，不受後續修改影響。系統會照所選值送出；廠商或模型若不支援，請求可能失敗並提示檢查思考程度與其他參數。OpenRouter 的通用 `reasoning.effort` 文件未列出 `ultra`，選用時尤其可能被拒絕。

每個模型也可設定「輸出 Token 上限」，新增時預設 32,768（可設 1–131,072）；既有模型在詳情修改。試跑使用該模型的上限；建立正式測試時留空覆寫欄位，即依各模型設定執行，或填入單次共同上限。建立測試後會保存當時的模型上限與覆寫值，之後修改模型不影響歷史測試及重跑。上限包含可能使用的推理 token，並非保證用滿；目錄若宣告較低上限，試跑或建立測試會提示調低。

驗證只讀取金鑰資訊，不產生推論；「試跑模型」與正式測試可能計費。完整金鑰操作、費用與重試規則見 [OpenRouter 使用說明](docs/openrouter.md)。

試跑完成後，視窗會保留明確的成功或失敗結果。成功時顯示模型回應、耗時，以及上游有回報時的費用／服務商；失敗時顯示原因。試跑成功只代表連線和文字回應正常，不代表回答品質通過評分。

試跑文字模型時，使用各模型設定的輸出上限；試跑視窗可設定網路連線／讀寫等待逾時（5–600 秒，預設 600 秒）。建立測試也可逐次設定，預設同為 600 秒；這不是整題總耗時的硬上限。若上游回傳空白文字與 `finish_reason=length`，只能確認上游表示長度限制，不能單憑此訊號認定推理 Token 用盡；正式測試的後續失敗紀錄會顯示安全的模型、用量與耗時診斷資訊。是否再次試跑由使用者決定，每次請求都可能計費。

不再使用的模型可從「我的模型 → 詳情 → 刪除模型」移除。確認後模型不再出現在清單，也不能再建立新測試；歷史測試結果保留。原目錄模型可重新加入，會取得新的模型 ID。

從 v0.1 升級時，先停止舊服務、安裝新的 requirements.lock，再重新啟動。Alembic 保留既有模型 ID 與測試結果；SQLite 自動備份仍須搭配 `.local-key` 保存。PostgreSQL 請先自行備份。

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
在「測試題庫 → 匯入題庫」先選來源。選「Hugging Face」後，再選要匯入的題庫；目前支援 [iKala / TMMLU+](https://huggingface.co/datasets/ikala/tmmluplus)，尚未支援任意 Hugging Face 資料集。預設選「官方最新版本」：每次預覽前取得當下的 `main` commit SHA 與驗證／測試集科目清單，再以該 SHA 讀取整次預覽的所有科目；匯入後每題保留確切 SHA 與原始連結。也可選固定 v1.1 重現舊版。TMMLU+ 可選單科或目前版本的全部科目，再選每科固定抽樣或完整驗證／測試分割；先預覽再加入題庫。全科抽樣每科最多 15 題；完整分割若超過 1000 題會自動建立整組分批題庫。固定 v1.1 單科下載失敗時，可從視窗中的官方連結下載 CSV，改由本機原始 CSV 入口預覽；本機檔案內容由使用者提供，系統不驗證它與官方檔案完全相同，因此不能標為最新官方 commit。資料集標示 MIT 授權，重新散布時請保留原授權聲明。

建立測試時可一次選整組分批題庫送出；每個 Run 最多 5000 個工作項目，整組最多 50000 次模型請求。介面會顯示預計請求數，使用者勾選費用提醒並按「開始測試」後才會呼叫模型。完整測試集約 19680 題；訓練集不包含在測試範圍。

不再需要的題庫可在「測試題庫」卡片按「刪除」並確認。刪除後不出現在題庫清單與新測試選單；分批題庫會整組移除。既有測試保留建立時的題目快照、結果與評分，不受刪除影響。

不再需要的測試紀錄可在「測試紀錄」列表或測試結果頁按「刪除」。同批次測試會一起移除；執行中的測試要先取消並等待工作停止。刪除後無法在介面檢視、匯出或重跑該紀錄，原始結果仍保留於本機資料庫供追溯。

選「本機檔案」可匯入自己的 JSON / CSV；讀取後會開啟題庫編輯畫面，可先檢查題目與名稱再儲存。檔案上限 5 MB、每次 1–1000 題。一般 CSV 逐題標記 `local_csv` 來源，不視為官方 TMMLU+ 內容。

TMMLU+ 使用「選擇題答案」規則，接受 `A`、`（A）`、`答案：A` 等單一選項格式；含解釋的長篇回答不自動判為通過。正式測試會呼叫所選模型，可能產生費用；可先用少量題目確認 Prompt 與評分結果。

一般 CSV：title,question,kind,expected（見 examples/basic.csv）。kind 可用 exact、contains、choice、manual；choice 的 expected 為 A、B、C 或 D。JSON Schema 或多輪訊息使用 JSON。
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
v0.2 尚無帳號權限、串流、工具執行、LLM Judge、跨 Run 回歸比較、預算控制與 MLCommons 整合。測試使用非串流 chat/completions 文字回應；只能產生圖片、音訊或 embedding 的模型尚無對應題型與評分。Auto Router 每題可能改用不同實際模型，排行榜標為動態路由，逐題結果可查看回傳模型；其目錄價格不能當作最終費用，結果只採用上游回報費用。
本專案獨立開發，未複製 MLCommons ModelBench 程式碼，亦無官方關聯。
詳見 docs/architecture.md、docs/verification.md、AGENTS.md。
