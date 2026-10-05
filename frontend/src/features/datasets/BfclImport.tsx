import { useEffect, useRef, useState } from "react";
import { api, type Case } from "../../api";

const categories: Record<string, string> = { simple: "單一工具", multiple: "多工具選擇", parallel: "多個調用", parallel_multiple: "混合多工具", irrelevance: "不相關工具" };
type Preview = { name: string; cases: Case[]; available: number; revision: string; counts: Record<string, number>; source_url: string; import_spec: Record<string, unknown>; preview_sha256: string };

export default function BfclImport({ onSaved }: { onSaved: () => void }) {
  const [latest, setLatest] = useState(false);
  const [selected, setSelected] = useState(Object.keys(categories));
  const [all, setAll] = useState(false);
  const [limit, setLimit] = useState(20);
  const [seed, setSeed] = useState(0);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => { setPreview(null); }, [latest, selected, all, limit, seed]);
  useEffect(() => () => request.current?.abort(), []);
  async function load() {
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(""); setPreview(null);
    try {
      const catalog = await api<{ revision: string }>(`/benchmarks/bfcl?latest=${latest}`, undefined, "GET", controller.signal);
      setPreview(await api<Preview>("/benchmarks/bfcl/preview", { revision: catalog.revision, categories: selected, limit: all ? null : limit, seed }, "POST", controller.signal));
    } catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "預覽失敗"); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function save() {
    if (!preview) return;
    setBusy(true); setError("");
    try { await api("/benchmarks/bfcl/import", { ...preview.import_spec, preview_sha256: preview.preview_sha256 }); onSaved(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "匯入失敗"); }
    finally { setBusy(false); }
  }
  return <div>
    <p className="form-note">測試模型是否選對工具與參數。第一版為 BFCL V3 Python 單輪子集，不代表完整官方排行榜。匯入與預覽不呼叫模型；開始測試才可能計費。</p>
    <div className="form-grid">
      <label>資料版本<select disabled={busy} value={latest ? "latest" : "fixed"} onChange={e => setLatest(e.target.value === "latest")}><option value="fixed">已確認的固定版本（V3）</option><option value="latest">HF 來源最新（V3 檔案）</option></select></label>
      <label>題目範圍<select disabled={busy} value={all ? "all" : "sample"} onChange={e => setAll(e.target.value === "all")}><option value="sample">每類固定抽樣</option><option value="all">所選類別全部題目</option></select></label>
      {!all && <><label>每類題數<input type="number" min={1} max={1000} disabled={busy} value={limit} onChange={e => setLimit(Number(e.target.value))} /></label><label>抽樣種子<input type="number" min={0} max={2147483647} disabled={busy} value={seed} onChange={e => setSeed(Number(e.target.value))} /></label></>}
    </div>
    <fieldset disabled={busy}><legend>測試類別</legend>{Object.entries(categories).map(([id, name]) => <label key={id} className="checkbox-label"><input type="checkbox" checked={selected.includes(id)} onChange={e => setSelected(e.target.checked ? [...selected, id] : selected.filter(v => v !== id))} />{name}</label>)}</fieldset>
    {error && <div className="alert error" role="alert">{error}</div>}
    <button className="secondary" disabled={busy || !selected.length || (!all && (limit < 1 || limit > 1000))} onClick={() => void load()}>{busy ? "處理中…" : "預覽題目"}</button>
    {preview && <>
      <p>{preview.cases.length} / {preview.available} 題 · Apache-2.0 · 版本 {preview.revision.slice(0, 12)} · <a href={preview.source_url} target="_blank" rel="noreferrer">查看來源</a></p>
      <p>{Object.entries(preview.counts).map(([id, count]) => `${categories[id]} ${count} 題`).join(" · ")}</p>
      <p className="form-note">只將題目與工具規格送給模型，參考答案留在評分端。不執行工具函式。下方最多預覽 10 題；超過 1000 題會分批儲存，可建立整批測試。</p>
      {preview.cases.slice(0, 10).map(item => <details key={item.title}><summary>{item.title}</summary>{item.messages.map((message, index) => <pre key={index}>{message.content}</pre>)}<strong>可用工具</strong><pre>{JSON.stringify(item.rule.bfcl?.functions, null, 2)}</pre></details>)}
      <button className="primary" disabled={busy} onClick={() => void save()}>確認匯入 {preview.cases.length} 題</button>
    </>}
  </div>;
}
