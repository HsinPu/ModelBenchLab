import { useEffect, useRef, useState } from "react";
import { api, type Case } from "../../api";

type Preview = {
  name: string;
  cases: Case[];
  revision: string;
  available: number;
  license: string;
  source_url: string;
};
export default function CodingImport({
  benchmark,
  onSaved,
}: {
  benchmark: "humaneval" | "humanevalplus";
  onSaved: () => void;
}) {
  const [latest, setLatest] = useState(false);
  const [all, setAll] = useState(false);
  const [limit, setLimit] = useState(20);
  const [seed, setSeed] = useState(0);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [runner, setRunner] = useState("正在檢查評分器狀態");
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api<{ available: boolean; reason?: string }>(
      "/coding/runner",
      undefined,
      "GET",
      controller.signal,
    )
      .then((data) =>
        setRunner(
          data.available
            ? "隔離 Python 評分器已就緒"
            : data.reason || "評分器尚未就緒",
        ),
      )
      .catch(() => {
        if (!controller.signal.aborted) setRunner("無法檢查評分器狀態");
      });
    return () => {
      controller.abort();
      request.current?.abort();
    };
  }, []);
  useEffect(() => {
    setPreview(null);
  }, [latest, all, limit, seed]);
  async function load() {
    setBusy(true);
    setError("");
    setPreview(null);
    const controller = new AbortController();
    request.current = controller;
    try {
      const catalog = await api<{ revision: string }>(
        `/benchmarks/coding/${benchmark}?latest=${latest}`,
        undefined,
        "GET",
        controller.signal,
      );
      setPreview(
        await api<Preview>(
          "/benchmarks/coding/preview",
          {
            benchmark,
            revision: catalog.revision,
            limit: all ? null : limit,
            seed,
          },
          "POST",
          controller.signal,
        ),
      );
    } catch (cause) {
      if (!controller.signal.aborted)
        setError(cause instanceof Error ? cause.message : "預覽失敗");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  async function save() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      await api("/datasets", { name: preview.name, cases: preview.cases });
      onSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "匯入失敗");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <p className="form-note">
        {runner}。匯入與預覽不呼叫模型；執行測試時才生成程式並計費。
      </p>
      <div className="form-grid">
        <label>
          資料版本
          <select
            disabled={busy}
            value={latest ? "latest" : "fixed"}
            onChange={(e) => setLatest(e.target.value === "latest")}
          >
            <option value="fixed">已確認的固定版本</option>
            <option value="latest">官方最新（每次預覽重新查詢）</option>
          </select>
        </label>
        <label>
          題目範圍
          <select
            disabled={busy}
            value={all ? "all" : "sample"}
            onChange={(e) => setAll(e.target.value === "all")}
          >
            <option value="sample">固定抽樣</option>
            <option value="all">完整題組（目前 164 題）</option>
          </select>
        </label>
        {!all && (
          <>
            <label>
              抽樣題數
              <input
                type="number"
                min={1}
                max={164}
                disabled={busy}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
              />
            </label>
            <label>
              抽樣種子
              <input
                type="number"
                min={0}
                max={2147483647}
                disabled={busy}
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
              />
            </label>
          </>
        )}
      </div>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      <button
        className="secondary"
        disabled={busy || (!all && (limit < 1 || limit > 164))}
        onClick={() => void load()}
      >
        {busy ? "處理中…" : "預覽題目"}
      </button>
      {preview && (
        <>
          <p>
            {preview.cases.length} / {preview.available} 題 · {preview.license}{" "}
            · 版本 {preview.revision.slice(0, 12)}{" "}
            <a href={preview.source_url} target="_blank" rel="noreferrer">
              查看來源
            </a>
          </p>
          <p className="form-note">
            只將題目與函式規格送給模型，測試案例保留在評分器。下方最多預覽前 10
            題。
          </p>
          {preview.cases.slice(0, 10).map((item) => (
            <details key={item.title}>
              <summary>{item.title}</summary>
              <pre>{item.rule.coding?.prompt}</pre>
            </details>
          ))}
          <button
            className="primary"
            disabled={busy}
            onClick={() => void save()}
          >
            確認匯入 {preview.cases.length} 題
          </button>
        </>
      )}
    </div>
  );
}
