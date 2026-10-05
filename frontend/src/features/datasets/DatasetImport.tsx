import { useState } from "react";
import { ArrowLeft, ArrowRight, Database, FileUp } from "lucide-react";
import type { Case } from "../../api";
import { parseDatasetFile } from "./parseDatasetFile";
import TmmluImport from "./TmmluImport";
import CodingImport from "./CodingImport";
import BfclImport from "./BfclImport";

type Source = "huggingface" | "file";
type Benchmark = "tmmluplus" | "humaneval" | "humanevalplus" | "bfcl";

const benchmarks: Record<Benchmark, { name: string; description: string; source: string }> = {
  bfcl: { name: "BFCL V3", description: "Python 單輪工具調用 · 工具選擇與參數正確性", source: "Gorilla / Berkeley-Function-Calling-Leaderboard" },
  humaneval: { name: "HumanEval", description: "164 題 Python 函式實作 · 隔離執行測試評分", source: "OpenAI / openai_humaneval" },
  humanevalplus: { name: "HumanEval+", description: "同一批 Python 題目 · 擴充測試檢查邊界案例", source: "EvalPlus / humanevalplus" },
  tmmluplus: {
    name: "TMMLU+",
    description: "繁體中文知識與推理選擇題 · 預設自動抓取最新版本",
    source: "iKala / tmmluplus",
  },
};

export default function DatasetImport({
  onSaved,
  onLocalFile,
}: {
  onSaved: () => void;
  onLocalFile: (file: File, cases: Case[]) => void;
}) {
  const [source, setSource] = useState<Source | null>(null);
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function chooseFile(file: File) {
    setBusy(true);
    setError("");
    try {
      onLocalFile(file, await parseDatasetFile(file));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "無法讀取題庫檔案");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dataset-import">
      <div className="import-progress" aria-label="匯入步驟">
        <span className={source ? "done" : "current"}>1 選擇來源</span>
        <span className={source && !benchmark ? "current" : benchmark ? "done" : ""}>2 {source === "file" ? "選擇檔案" : "選擇題庫"}</span>
        <span className={benchmark ? "current" : ""}>3 {source === "file" ? "檢查與儲存" : "設定與預覽"}</span>
      </div>

      {!source && (
        <>
          <p className="import-intro">選擇題庫來源。匯入前可以先檢查題目，確認後再儲存。</p>
          <div className="import-options">
            <button type="button" className="import-option" onClick={() => setSource("huggingface")}>
              <Database size={20} aria-hidden="true" />
              <span><strong>Hugging Face</strong><small>從已支援的公開題庫選擇資料集</small></span>
              <ArrowRight size={17} aria-hidden="true" />
            </button>
            <button type="button" className="import-option" onClick={() => setSource("file")}>
              <FileUp size={20} aria-hidden="true" />
              <span><strong>本機檔案</strong><small>匯入自己的 JSON 或 CSV 題庫</small></span>
              <ArrowRight size={17} aria-hidden="true" />
            </button>
          </div>
        </>
      )}

      {source === "huggingface" && !benchmark && (
        <>
          <button type="button" className="import-back" onClick={() => setSource(null)}><ArrowLeft size={15} /> 返回來源</button>
          <h3 className="import-heading">選擇要匯入的題庫</h3>
          <p className="import-intro">目前支援下列 Hugging Face 題庫；其他資料集尚未開放匯入。</p>
          <div className="import-options">
            {(Object.entries(benchmarks) as [Benchmark, typeof benchmarks[Benchmark]][]).map(([id, item]) => (
              <button key={id} type="button" className="import-option" onClick={() => setBenchmark(id)}>
                <Database size={20} aria-hidden="true" />
                <span><strong>{item.name}</strong><small>{item.description}</small><small>來源：{item.source}</small></span>
                <ArrowRight size={17} aria-hidden="true" />
              </button>
            ))}
          </div>
        </>
      )}

      {source === "huggingface" && benchmark === "tmmluplus" && (
        <>
          <button type="button" className="import-back" onClick={() => setBenchmark(null)}><ArrowLeft size={15} /> 返回題庫選擇</button>
          <h3 className="import-heading">TMMLU+ · 設定匯入內容</h3>
          <TmmluImport onSaved={onSaved} />
        </>
      )}

      {source === "huggingface" && (benchmark === "humaneval" || benchmark === "humanevalplus") && (
        <>
          <button type="button" className="import-back" onClick={() => setBenchmark(null)}><ArrowLeft size={15} /> 返回題庫選擇</button>
          <h3 className="import-heading">{benchmarks[benchmark].name} · 設定匯入內容</h3>
          <CodingImport key={benchmark} benchmark={benchmark} onSaved={onSaved} />
        </>
      )}
      {source === "huggingface" && benchmark === "bfcl" && <>
        <button type="button" className="import-back" onClick={() => setBenchmark(null)}><ArrowLeft size={15} /> 返回題庫選擇</button>
        <h3 className="import-heading">BFCL V3 · 設定匯入內容</h3>
        <BfclImport onSaved={onSaved} />
      </>}
      {source === "file" && (
        <>
          <button type="button" className="import-back" onClick={() => { setSource(null); setError(""); }}><ArrowLeft size={15} /> 返回來源</button>
          <h3 className="import-heading">選擇本機題庫檔案</h3>
          <p className="import-intro">支援 JSON 題目陣列或包含 title、question、kind、expected 欄位的 CSV。讀取後可在編輯畫面檢查，再儲存為題庫版本。</p>
          {error && <div role="alert" className="alert error">{error}</div>}
          <label>
            JSON / CSV 檔案（最多 5 MB、1000 題）
            <input type="file" accept=".json,.csv,application/json,text/csv" disabled={busy} onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void chooseFile(file);
              event.target.value = "";
            }} />
          </label>
          {busy && <p className="form-note" role="status">正在讀取題庫…</p>}
        </>
      )}
    </div>
  );
}
