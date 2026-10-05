# Coding 題庫與隔離評分

## 操作

1. 在題庫匯入選 Hugging Face，再選 HumanEval 或 HumanEval+。
2. 選已確認的固定版本，或官方最新；選完整題組或固定種子抽樣。每次「官方最新」預覽均先查 metadata，再以確切 SHA 下載。預览只顯示前 10 題；確認後保存所選全部題目。
3. Docker Desktop 切換 Linux containers，執行 `scripts/build-coding-runner.ps1`。API 與 Worker 都需可操作該本機 Docker 引擎；檢查 `/api/coding/runner`。
4. 從 Coding 題庫卡片建立測試，選模型及適合生成程式的 Prompt。程式執行上限預設 10 秒（1–120），與網路等待及模型 Token 上限分開；第一版每題生成一次，拒絕多次抽樣。
5. 結果頁可分別篩選未通過、執行失敗、評分失敗。展開回答可查看實際執行的程式、評分版本與耗時。整場完成後可「重新評分（不重新生成）」。

匯入及 Docker 評分不會呼叫模型；按開始測試後的生成可能計費。未設定思考程度時仍照既有行為不送參數。

## 固定來源與重現

| 題庫 | HF repo | 已確認 SHA | 格式 | 授權 |
| --- | --- | --- | --- | --- |
| HumanEval | openai/openai_humaneval | 7dce6050a7d6d172f3cc5c32aa97f52fa1a2e544 | 官方 Parquet | MIT |
| HumanEval+ | evalplus/humanevalplus | d32357cf319e50e9c8d8dab5ea876c72b0fd321b | test.jsonl | Apache-2.0 |

僅接受上述白名單 repo 與檔案位置，不下載或執行資料集 Python 載入腳本。單次下載最多 20 MB，1–164 題；入口函式、task ID、題目長度及測試長度均驗證。官方若改變格式或超出限制，匯入會明確失敗，不自行猜測欄位。

每題保存 task ID、prompt、入口函式、測試內容及 SHA-256、repo、commit SHA、來源連結、授權、抽樣種子。測試與參考解答不進入模型 messages，且參考解答不保存於匯入題库。Run v3 保存完整題庫及評分設定快照；普通文字 Run 仍為 v2。沒有新增 ORM 欄位，使用既有 JSON 欄位，不需要資料表 migration。

資料列表及預設 Run 詳情不傳大型測試正文，避免輪詢反覆傳輸 HumanEval+ 的約 11 MB 測試。完整內容留在資料庫快照；JSON 匯出與 `?include_tests=true` 的詳情可追溯。

## 生成與評分生命週期

Worker 條件 claim → 呼叫模型 → 條件保存回答、用量、費用及 pending 評分 → Docker 執行 → 條件完成。

`Item.status=running` 加上 `result.evaluation.pending=true` 表示評分中。Worker 中斷後的 stale recovery 不重新呼叫模型：已保存回答的項目改為完成但評分失敗，使用者可明確重評。沒有回答的未知 API 呼叫仍依既有規則標失敗，避免自動重播造成重複計費。重新評分以條件更新重新排隊，沿用原回答、測試、runtime 和 timeout，保留 attempts 與已回報費用；重複派送無法重新生成。

| 情況 | Item | evaluation.passed | 分類 |
| --- | --- | --- | --- |
| 全部 assert 通過 | completed | true | 通過 |
| 答錯／語法錯誤／執行錯誤／程式時間或記憶體超限 | completed | false | 未通過 |
| 模型 API／傳輸失敗 | failed | 無評分 | 執行失敗 |
| 映像不存在／Docker 異常／測試套件異常／評分 Worker 中斷 | completed | null，error=true | 評分失敗 |
| 強制取消 | cancelled | 不接受晚到評分 | 已取消 |

一般取消保留已送出生成與其評分；強制取消會終結整個 batch，輪詢取消狀態後刪除該題的容器並中止本機等待。已保存回答與費用保留，晚到結果不得覆寫 cancelled。Docker daemon 故障可能阻止容器清理；關閉本機 HTTP 也不能保證廠商停止生成或計費。

## 隔離執行

映像使用固定 Python 3.12 基底 digest 與 numpy 2.2.6。Run 記錄實際 image ID、runner 版本 `hf-tests-v1`、Python／numpy 版本、512 MB 與 1 CPU；不在評分時自動 pull 或改換映像。重建成不同 ID 的映像後，新舊 Run 不混排名。

每題獨立容器：非 root、network none、唯讀 root filesystem、cap-drop ALL、no-new-privileges、64 PID、512 MB（無額外 swap）、1 CPU、64 MB tmpfs、128 個檔案描述符。不掛載專案、金鑰、資料庫或 Docker socket；候選程式只在容器內的子程序執行，宿主只做文字／AST 解析及 Docker 控制。輸出從 supervisor 取得固定結果碼，不回傳候選程式 stdout、stderr、任意例外文字或系統路徑。

這是本機功能正確性評分環境，不是對抗式防作弊或惡意程式分析環境；Docker 共用引擎核心，不能宣稱絕對安全。宿主 API／Worker 本身需要 Docker 權限，但不會將該權限交給候選容器。

## 成績範圍及限制

同一不可變題庫、相同 image ID／runtime 與 code timeout 才合併比較；HumanEval 與 HumanEval+ 分開。每模型沿用既有「最近一次涵蓋全部題目」規則。程式題只有全部題目得到布林評分，且每題一次時列正式名次與 pass@1；有 API 失敗或評分失敗時僅顯示已評分通過率與 coverage，不列正式名次。抽樣的 pass@1 只代表該份抽樣題庫，不等於官方 164 題完整成績。

HumanEval+ 執行 HF 該固定版本提供的自包含 `check(candidate)` 擴充測試，不使用官方 EvalPlus CLI 的完整 harness／動態參考耗時／額外工具鏈。此結果不能直接宣稱與官方排行榜完全可比。重評只使用原測試；第一版尚無將舊 HumanEval 回答套到不同 HumanEval+ 題庫的跨套件重評，也沒有 pass@k、多語言、SWE-bench 或 LiveCodeBench。Compose 容器尚未配置 Docker CLI／daemon 存取，會在建立 Coding Run 前拒絕，沒有宿主直接執行 fallback。

來源：[OpenAI HumanEval](https://github.com/openai/human-eval)、[HumanEval HF](https://huggingface.co/datasets/openai/openai_humaneval)、[EvalPlus HF](https://huggingface.co/datasets/evalplus/humanevalplus)、[EvalPlus](https://github.com/evalplus/evalplus)。

## 可重跑驗證

```powershell
# 在 backend/ 執行，真實 Docker 測試使用合成程式，不呼叫模型
$env:TEST_CODING_DOCKER='1'
..\.venv\Scripts\python.exe -m pytest -q
# 在 repository 根目錄，下載固定版本並檢查參考解答
.\.venv\Scripts\python.exe scripts/verify-coding.py --questions 10
```

實際驗證結果見 [verification.md](verification.md)。
