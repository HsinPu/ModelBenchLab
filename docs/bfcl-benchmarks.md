# BFCL V3 工具調用測試

## 操作與範圍

題庫 → 匯入 → Hugging Face → BFCL V3。可選五類 Python 單輪題目：單一工具、多工具選擇、多個調用、混合多工具、不相關工具。可複選類別、每類固定種子抽樣或選全部；先預覽再儲存。匯入不呼叫模型。

固定 HF repo `gorilla-llm/Berkeley-Function-Calling-Leaderboard`，已確認版本 `61fc0608cfd831fcfbbaa676ebdfef0ed963eeda`。來源最新每次預覽重查 metadata 並固定 SHA，僅識別 BFCL_v3 檔案，不假稱 HF 最新等於完整 BFCL V4。來源資料 Apache-2.0。下載每檔最多 5 MB／2000 列，單次最多 10000 題，不執行資料集載入腳本。

目前五類共 1240 題：simple 400、multiple 200、parallel 200、parallel_multiple 200、irrelevance 240。完整題組沿用既有分批題庫，1000+240 題，可一次建立整批測試；也可匯入較小抽樣題庫。

預覽不回傳參考答案。儲存透過 `/api/benchmarks/bfcl/import`，僅送確切 SHA、類別、抽樣設定與 preview SHA-256；後端重建同一內容並核對雜湊才存入題庫。避免 JavaScript 把 1.0 改成 1，或把超過安全整數範圍的答案改值；不接受瀏覽器轉送的答案資料。

建立測試選支援原生工具調用的模型與合適 Prompt，第一版每題一次。OpenRouter 若目錄明確未宣告 tools，建立測試時拒絕；自訂相容端點由 API 實際回應判定，不自行改成文字模擬調用或換模型。匯入與評分不計模型費用，開始生成才可能計費。

## 工具傳輸與評分

模型只收到題目 messages 與工具規格 tools，參考答案不送入 messages／payload。工具原名可能含點號、過長或有衝突，所以使用每題穩定的 `bfcl_0`、`bfcl_1` 別名；description 保留原名。JSON Schema 轉換 dict→object、float→number、tuple→array、any→省略 type。回應原生 tool_calls 的別名在評分前還原，完整對照由 Run 不可變函式規格可重建。

型別轉換只遍歷 Schema 定義位置（如 properties、items、組合條件與 $defs），不轉換 enum、const、default、examples 或擴充欄位中的資料值，也不修改 Run 保存的原始規格。候選整數在官方浮點比較時溢位，記為未通過／numeric_range；真正的評分器例外仍記為評分失敗。

回應僅保留工具名稱與 arguments 字串、文字，以及原有 allowlist 用量／費用／路由資料；不保存原始上游回應或推理內容。有效 tool_calls 只有工具沒有文字仍是正常回應；不相關題目則須有正常文字回應且沒有調用。錯誤 JSON 參數、選錯工具、數量不符屬未通過；API／格式失敗與評分器失敗分開。官方規則對某些字串允許大小寫及標點正規化，對多個平行調用不要求排列相同。

評分器採 Gorilla commit `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` 的 Python AST comparison。原始碼保留於 `backend/app/bfcl_checker_source.txt`，來源 SHA 與雜湊在 `bfcl_checker_provenance.json`，授權在 `BFCL-LICENSE`。Python-only adapter 移除 Java／JavaScript 分支及模型名稱登錄；工具別名由 adapter 還原，保留 Python 值、型別、多工具與平行匹配比較邏輯。不執行模型輸出的程式、函式、eval 或真實 API 工具。

Run v4 保存完整題庫（含標準答案、內容雜湊、HF SHA）、模型／Prompt 快照與 native-tools 模式、固定 checker commit、adapter 檔案雜湊。使用現有 JSON 欄位，沒有 ORM／Schema 欄位遷移；舊 Run 不變。一般詳情和題庫列表省略 answers，完整 JSON 匯出仍可追溯。

模型回答與費用先保存再評分；重新評分／評分中斷恢复沿用已保存 tool_calls，不重新生成。評分版本變動時明確報評分失敗，不用新版本悄悄覆蓋舊 Run。取消與強制取消沿用条件更新，晚到回應不能覆寫已取消項目。

## 成績

逐題可檢視工具、參數、評分類別、版本與錯誤類型。總覽合併同一不可變題庫及同一 bfcl_runtime，顯示整體與每類已評分正確率；全部題目每題一次且可評分才列正式名次。API 失敗、評分失敗、取消不進分母，部分成績不列正式名次。Demo 仍標示示範／模擬。

排名範圍依題庫的 bundle 識別決定；即使從 API 建立單一批次測試，仍須涵蓋整組題庫才納入題庫排行榜。缺少其餘批次時不產生正式成績；若已有完整測試，保留該完整測試的成績，不讓較新的部分測試取代它。單次測試結果仍可在測試紀錄檢視。

這是 BFCL V3 Python 單輪子集與本工具的原生 API adapter 成績，不是完整 BFCL 官方排行榜分數；未涵蓋 live、Java／JavaScript、execution、多輪、記憶、搜尋或長時間 Agent 工作。

## 驗證

`scripts/verify-bfcl.py` 從固定 HF SHA 下載全部題目，以允許的參考參數構造調用並檢查固定評分器；不呼叫模型、不寫入資料庫。參考調用省略官方允許省略的可選參數，保留原始答案不修正。後端測試用合成資料與 HTTPX MockTransport，涵蓋工具選擇／參數、原生無文字回應、抽樣、快照、重新評分及排名。實測結果與限制見 verification.md。
