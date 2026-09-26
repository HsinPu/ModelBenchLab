import { useEffect, useRef, useState } from "react";
import { api, Case } from "../../api";

type Catalog = {
  revision: string;
  subjects: string[];
  source_url: string;
  license: string;
  last_modified?: string;
};
type Preview = {
  name: string;
  cases: Case[];
  revision: string;
  available: number;
  source_url: string;
  license: string;
  imported_from: string;
  subject_count?: number;
};

const labels: Record<string, string> = {
  computer_science: "資訊科學",
  logic_reasoning: "邏輯推理",
  geography_of_taiwan: "台灣地理",
  chinese_language_and_literature: "國文與文學",
  junior_math_exam: "國中數學",
  junior_chinese_exam: "國中國文",
  junior_social_studies: "國中社會",
  junior_science_exam: "國中自然",
  taiwanese_hokkien: "臺灣閩南語",
};

export default function TmmluImport({ onSaved }: { onSaved: () => void }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [latestCatalog, setLatestCatalog] = useState<Catalog | null>(null);
  const [version, setVersion] = useState<"latest" | "v1.1">("latest");
  const [scope, setScope] = useState<"one" | "all">("one");
  const [quantity, setQuantity] = useState<"sample" | "complete">("sample");
  const [subject, setSubject] = useState("computer_science");
  const [split, setSplit] = useState<"validation" | "test">("validation");
  const [limit, setLimit] = useState(50);
  const [perSubject, setPerSubject] = useState(5);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [totalSubjects, setTotalSubjects] = useState(1);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    api<Catalog>("/benchmarks/tmmluplus")
      .then(setCatalog)
      .catch((e) => setError(e instanceof Error ? e.message : "無法載入科目"));
  }, []);
  useEffect(() => {
    if (version !== "latest") return;
    const controller = new AbortController();
    api<Catalog>("/benchmarks/tmmluplus/latest", undefined, "GET", controller.signal)
      .then(setLatestCatalog)
      .catch((e) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "無法取得最新版本"); });
    return () => controller.abort();
  }, [version]);
  useEffect(() => () => request.current?.abort(), []);

  async function load(csvText?: string, selection?: { subject: string; split: "validation" | "test" }) {
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    setPreview(null);
    setProgress(0);
    try {
      const resolved = csvText !== undefined || version === "v1.1"
        ? catalog
        : await api<Catalog>("/benchmarks/tmmluplus/latest", undefined, "GET", controller.signal);
      if (!resolved) throw new Error("無法取得 TMMLU+ 科目清單");
      const resolvedRevision = resolved.revision;
      if (version === "latest" && csvText === undefined) setLatestCatalog(resolved);
      const subjects = selection ? [selection.subject] : scope === "all" ? resolved.subjects : [subject];
      if (subjects.some((item) => !resolved.subjects.includes(item))) {
        throw new Error("所選科目已不在此版本，請重新選擇科目");
      }
      setTotalSubjects(subjects.length);
      const selectedSplit = selection?.split ?? split;
      const selectedLimit = quantity === "complete"
        ? null : scope === "all" && !selection ? perSubject : limit;
      const results: Preview[] = new Array(subjects.length);
      let next = 0;
      let completed = 0;
      async function worker() {
        while (next < subjects.length && !controller.signal.aborted) {
          const index = next++;
          results[index] = await api<Preview>("/benchmarks/tmmluplus/preview", {
            subject: subjects[index], split: selectedSplit, limit: selectedLimit, revision: resolvedRevision,
            ...(csvText === undefined ? {} : { csv_text: csvText }),
          }, "POST", controller.signal);
          completed++;
          setProgress(completed);
        }
      }
      await Promise.all(Array.from({ length: Math.min(3, subjects.length) }, () => worker()));
      if (controller.signal.aborted) return;
      const cases = results.flatMap((result) => result.cases);
      setPreview(subjects.length === 1 ? results[0] : {
        name: `TMMLU+ ${resolved.revision.slice(0, 12)} · 全 ${subjects.length} 科 · ${selectedSplit} · ${cases.length} 題`,
        cases,
        revision: resolved.revision,
        available: results.reduce((sum, result) => sum + result.available, 0),
        source_url: resolved.source_url,
        license: resolved.license,
        imported_from: "official_download",
        subject_count: subjects.length,
      });
    } catch (e) {
      controller.abort();
      setError(e instanceof Error ? e.message : "無法讀取 TMMLU+ 題目");
    } finally {
      if (request.current === controller) request.current = null;
      setBusy(false);
    }
  }

  async function fromFile(file: File) {
    const match = /^(.+)_(val|test)\.csv$/i.exec(file.name);
    if (!match || !catalog?.subjects.includes(match[1])) {
      setError("請選擇 TMMLU+ 原始 CSV，檔名應為「科目_val.csv」或「科目_test.csv」");
      return;
    }
    const nextSplit = match[2].toLowerCase() === "val" ? "validation" : "test";
    setSubject(match[1]);
    setSplit(nextSplit);
    setScope("one");
    try {
      await load(await file.text(), { subject: match[1], split: nextSplit });
    } catch {
      setError("無法讀取 CSV 檔案");
    }
  }

  async function save() {
    if (!preview || busy) return;
    setBusy(true);
    setError("");
    try {
      await api(preview.cases.length > 1000 ? "/datasets/batch" : "/datasets", {
        name: preview.name.slice(0, preview.cases.length > 1000 ? 80 : 100),
        cases: preview.cases,
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "儲存題庫失敗");
    } finally {
      setBusy(false);
    }
  }

  const sourceFile = `${subject}_${split === "validation" ? "val" : "test"}.csv`;
  const sourceUrl = `https://huggingface.co/datasets/ikala/tmmluplus/blob/v1.1/data/${sourceFile}`;
  const activeSubjects = version === "latest" ? (latestCatalog?.subjects ?? catalog?.subjects ?? []) : (catalog?.subjects ?? []);
  const currentRevision = preview?.revision ?? (version === "latest" ? latestCatalog?.revision : catalog?.revision);

  return (
    <div className="tmmlu-import">
      <p className="form-note">
        從 iKala 的 TMMLU+ 匯入繁體中文四選一題目。預設在每次預覽時抓取官方最新版本，並將所有科目固定在同一個 commit；匯入本身不會呼叫模型。
      </p>
      {error && <div role="alert" className="alert error">{error}</div>}
      <div className="form-grid">
        <label>
          資料版本
          <select value={version} disabled={busy} onChange={(e) => { setVersion(e.target.value as "latest" | "v1.1"); setPreview(null); setError(""); }}>
            <option value="latest">官方最新版本（自動更新）</option>
            <option value="v1.1">固定 v1.1（可重現舊測試）</option>
          </select>
        </label>
        <label>
          科目範圍
          <select value={scope} disabled={busy} onChange={(e) => { setScope(e.target.value as "one" | "all"); setPreview(null); }}>
            <option value="one">單一科目</option>
            <option value="all">全部 {activeSubjects.length || 66} 科</option>
          </select>
        </label>
        <label>
          題目數量
          <select value={quantity} disabled={busy} onChange={(e) => { setQuantity(e.target.value as "sample" | "complete"); setPreview(null); }}>
            <option value="sample">每科固定抽樣</option>
            <option value="complete">所有題目（完整分割）</option>
          </select>
        </label>
      </div>
      <div className="form-grid">
        {scope === "one" && <label>
          科目
          <select value={subject} disabled={!catalog || busy} onChange={(e) => { setSubject(e.target.value); setPreview(null); }}>
            {(activeSubjects.length ? activeSubjects : [subject]).map((item) => (
              <option key={item} value={item}>{labels[item] ? `${labels[item]} · ` : ""}{item.replaceAll("_", " ")}</option>
            ))}
          </select>
        </label>}
        <label>
          題目分割
          <select value={split} disabled={busy} onChange={(e) => { setSplit(e.target.value as "validation" | "test"); setPreview(null); }}>
            <option value="validation">驗證集（建議先試）</option>
            <option value="test">測試集</option>
          </select>
        </label>
      </div>
      {quantity === "sample" && (scope === "one" ? (
        <label>
          最多匯入題數（1–1000，固定抽樣可重現）
          <input type="number" min={1} max={1000} value={limit} disabled={busy} onChange={(e) => { setLimit(Number(e.target.value)); setPreview(null); }} />
        </label>
      ) : (
        <label>
          每科最多抽樣（1–15 題；目前 {activeSubjects.length || 66} 科）
          <input type="number" min={1} max={15} value={perSubject} disabled={busy} onChange={(e) => { setPerSubject(Number(e.target.value)); setPreview(null); }} />
        </label>
      ))}
      {scope === "all" && <p className="form-note">
        全科模式會讀取所選版本的 {activeSubjects.length || 66} 份官方檔案。完整題目將分成多個題庫版本，建立測試時可一次送出所有批次；正式模型測試可能產生大量費用。
      </p>}
      <button type="button" className="secondary full" disabled={!catalog || busy || (quantity === "sample" && (scope === "one" ? limit < 1 || limit > 1000 : perSubject < 1 || perSubject > 15))} onClick={() => load()}>
        {busy ? `載入中… ${progress}/${totalSubjects} 科` : "從官方來源預覽"}
      </button>
      {scope === "one" && version === "v1.1" && <p className="form-note">
        下載失敗時，可從 <a href={sourceUrl} target="_blank" rel="noreferrer">官方頁面下載 {sourceFile}</a>，再選擇該 CSV 檔案。
      </p>}
      {scope === "one" && version === "v1.1" && <label>
        從本機 TMMLU+ CSV 預覽
        <input type="file" accept=".csv,text/csv" disabled={!catalog || busy} onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void fromFile(file);
          e.target.value = "";
        }} />
      </label>}
      {preview && (
        <div className="tmmlu-preview">
          <strong>預覽完成：{preview.cases.length} 題{preview.subject_count ? ` · ${preview.subject_count} 科` : ""}</strong>
          <p>資料版本：<a href={`https://huggingface.co/datasets/ikala/tmmluplus/tree/${preview.revision}`} target="_blank" rel="noreferrer">{preview.revision}</a></p>
          <p>來源分割共 {preview.available} 題；{quantity === "sample" ? "已固定抽樣" : "已包含完整題目"}。評分會辨識單一選項字母與「答案：A」格式。</p>
          {preview.cases.length > 1000 && <p>將自動分成 {Math.ceil(preview.cases.length / 1000)} 個題庫批次；建立測試時可一次選取整組。</p>}
          <label>
            題庫名稱
            <input value={preview.name} maxLength={preview.cases.length > 1000 ? 80 : 100} onChange={(e) => setPreview({ ...preview, name: e.target.value })} />
          </label>
          <ol>
            {preview.cases.slice(0, 3).map((item) => <li key={item.title}>{item.title}：{item.messages[0]?.content.split("\n")[0]}</li>)}
          </ol>
          <button type="button" className="primary full" disabled={busy || !preview.name.trim()} onClick={save}>
            {busy ? "儲存中…" : `加入題庫（${preview.cases.length} 題）`}
          </button>
        </div>
      )}
      <p className="form-note">
        資料來源：<a href={catalog?.source_url || "https://huggingface.co/datasets/ikala/tmmluplus"} target="_blank" rel="noreferrer">iKala / TMMLU+</a> · {currentRevision || "載入中"} · {catalog?.license || "MIT"} 授權。每題會保存來源版本。最新版本須由官方直接下載；本機 CSV 可使用固定 v1.1 預覽。
      </p>
    </div>
  );
}
