import { useEffect, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronRight,
  Database,
  FlaskConical,
  Layers3,
  LayoutDashboard,
  Plus,
  Play,
  RefreshCw,
  Settings2,
  Sparkles,
  Terminal,
  TextCursorInput,
  X,
} from "lucide-react";
import { api, Model, Dataset, Prompt, Run, Detail, Case, Item } from "./api";

const labels: Record<string, string> = {
  queued: "等待執行",
  running: "執行中",
  completed: "已完成",
  completed_with_errors: "完成 · 部分失敗",
  failed: "執行失敗",
  cancelling: "取消中",
  cancelled: "已取消",
};
const active = (s: string) => ["queued", "running", "cancelling"].includes(s);
const formatTime = (s: string) =>
  new Date(s).toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
const initialCase: Case = {
  title: "新題目",
  messages: [{ role: "user", content: "" }],
  rule: { kind: "contains", expected: "" },
  tags: [],
};

function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status}>
      <i />
      {labels[status] || status}
    </span>
  );
}

export default function App() {
  const [page, setPage] = useState("overview");
  const [models, setModels] = useState<Model[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [modal, setModal] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(false);
  const [filter, setFilter] = useState("all");
  const [modelForm, setModelForm] = useState({
    name: "",
    provider: "openai-compatible",
    model: "",
    endpoint: "http://localhost:11434/v1",
    api_key: "",
  });
  const [datasetName, setDatasetName] = useState("");
  const [cases, setCases] = useState<Case[]>([{ ...initialCase }]);
  const [jsonMode, setJsonMode] = useState(false);
  const [caseJson, setCaseJson] = useState("");
  const [promptForm, setPromptForm] = useState({ name: "", text: "" });
  const [runForm, setRunForm] = useState({
    name: "",
    dataset_id: "",
    prompt_id: "",
    model_ids: [] as string[],
    repeats: 1,
    temperature: 0,
    max_tokens: 512,
    timeout: 60,
  });
  const [reviewItem, setReviewItem] = useState<Item | null>(null);
  const [reviewScore, setReviewScore] = useState(4);
  const [reviewNote, setReviewNote] = useState("");
  async function refresh() {
    const [m, d, p, r] = await Promise.all([
      api<Model[]>("/models"),
      api<Dataset[]>("/datasets"),
      api<Prompt[]>("/prompts"),
      api<Run[]>("/runs"),
    ]);
    setModels(m);
    setDatasets(d);
    setPrompts(p);
    setRuns(r);
    setOnline(true);
  }
  useEffect(() => {
    refresh().catch((e) => {
      setError(e.message);
      setOnline(false);
    });
  }, []);
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(() => {
    if (!runs.some((r) => active(r.status))) return;
    const t = setInterval(() => refresh().catch(() => {}), 2500);
    return () => clearInterval(t);
  }, [runs]);
  useEffect(() => {
    if (!detail || !active(detail.status)) return;
    const source = new EventSource("/api/runs/" + detail.id + "/events");
    source.onmessage = () => {
      api<Detail>("/runs/" + detail.id)
        .then(setDetail)
        .catch(() => {});
    };
    return () => source.close();
  }, [detail?.id, detail?.status]);
  async function action(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失敗");
    } finally {
      setBusy(false);
    }
  }
  async function openRun(id: string) {
    await action(async () => {
      setDetail(await api<Detail>("/runs/" + id));
      setPage("detail");
      setFilter("all");
    });
  }
  function newRun() {
    setRunForm({
      name: "模型比較 · " + new Date().toLocaleDateString("zh-TW"),
      dataset_id: datasets[0]?.id || "",
      prompt_id: prompts[0]?.id || "",
      model_ids: models.filter((m) => m.provider === "demo").map((m) => m.id),
      repeats: 1,
      temperature: 0,
      max_tokens: 512,
      timeout: 60,
    });
    setModal("run");
  }
  function newDataset(d?: Dataset) {
    setDatasetName(d ? d.name + " · 新版本" : "");
    setCases(
      d
        ? JSON.parse(JSON.stringify(d.cases))
        : [
            {
              ...initialCase,
              messages: [{ role: "user", content: "" }],
              rule: { kind: "contains", expected: "" },
            },
          ],
    );
    setJsonMode(false);
    setModal("dataset");
  }
  const selectedDataset = datasets.find((d) => d.id === runForm.dataset_id);
  const requests =
    (selectedDataset?.cases.length || 0) *
    runForm.model_ids.length *
    runForm.repeats;
  const titles: Record<string, string> = {
    overview: "評估總覽",
    runs: "測試紀錄",
    models: "模型管理",
    datasets: "測試題庫",
    prompts: "Prompt 版本",
    detail: "測試結果",
  };
  const graded = runs.reduce((s, r) => s + r.graded, 0),
    passed = runs.reduce((s, r) => s + r.passed, 0);
  function runTable(list: Run[]) {
    return list.length ? (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>測試名稱</th>
              <th>狀態</th>
              <th>模型</th>
              <th>通過率</th>
              <th>建立時間</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.map((r) => (
              <tr
                key={r.id}
                onClick={() => openRun(r.id)}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter") openRun(r.id);
                }}
              >
                <td>
                  <strong>{r.name}</strong>
                  <small>
                    {r.dataset_name} · {r.total} 個工作
                  </small>
                </td>
                <td>
                  <Badge status={r.status} />
                </td>
                <td>
                  <span className="mono">{r.models.length} models</span>
                </td>
                <td>
                  <strong>
                    {r.pass_rate === null ? "—" : r.pass_rate + "%"}
                  </strong>
                </td>
                <td className="muted">{formatTime(r.created_at)}</td>
                <td>
                  <ChevronRight size={16} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <div className="empty">
        <FlaskConical size={34} />
        <h3>你的第一場模型實驗，從這裡開始</h3>
        <p>已準備好 10 題示範題庫與兩個示範模型，不需要 API Key。</p>
        <button className="primary" onClick={newRun}>
          <Play size={16} />
          建立第一個測試
        </button>
      </div>
    );
  }
  function answerCard(item: Item | undefined, model: Model) {
    if (!item)
      return (
        <div className="answer" key={model.id}>
          <h4>{model.name}</h4>
          <p className="muted">此重跑未包含這個項目</p>
        </div>
      );
    const result = item.result;
    const ev = result?.evaluation;
    const review = detail?.reviews.filter((r) => r.item_id === item.id).at(-1);
    return (
      <div className="answer" key={model.id}>
        <div className="answer-head">
          <strong>{model.name}</strong>
          {result ? (
            <span
              className={
                "pill " +
                (ev?.passed === true
                  ? "good"
                  : ev?.passed === false
                    ? "bad"
                    : "neutral")
              }
            >
              {ev?.passed === true
                ? "通過"
                : ev?.passed === false
                  ? "未通過"
                  : review
                    ? "人工已評"
                    : "待評分"}
            </span>
          ) : (
            <Badge status={item.status} />
          )}
        </div>
        <pre>
          {result?.output ||
            item.attempts.at(-1)?.error ||
            (item.status === "queued"
              ? "等待 Worker 執行…"
              : item.status === "running"
                ? "正在生成回答…"
                : "尚無回答")}
        </pre>
        {result && (
          <>
            <div className="answer-meta">
              <span>{result.latency_ms} ms</span>
              <span>
                {result.output_tokens === null
                  ? "Token 未提供"
                  : result.output_tokens + " output tokens"}
              </span>
              {result.demo && <span>示範資料</span>}
            </div>
            <div className="reason">
              {review && ev?.passed === null
                ? "已記錄人工評分；不納入自動通過率"
                : ev?.reason}
            </div>
            <div className="review-line">
              <button
                className="text-button"
                onClick={() => {
                  setReviewItem(item);
                  setReviewScore(review?.score || 4);
                  setReviewNote(review?.note || "");
                  setModal("review");
                }}
              >
                {review ? "人工評分 " + review.score + "/5" : "＋ 人工評分"}
              </button>
              {ev?.error && (
                <button
                  className="text-button"
                  onClick={() =>
                    action(async () => {
                      await api("/items/" + item.id + "/evaluate", {});
                      setDetail(await api("/runs/" + detail!.id));
                    })
                  }
                >
                  重新評分
                </button>
              )}
            </div>
            {review?.note && <small>{review.note}</small>}
          </>
        )}
      </div>
    );
  }
  return (
    <div className="shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("overview");
          }}
        >
          <span className="brand-icon">
            <FlaskConical size={22} />
          </span>
          <span>
            ModelBench<span className="brand-lab">Lab</span>
            <small>MODEL EVALUATION WORKSPACE</small>
          </span>
        </a>
        <div className="workspace">
          <span className="avatar">M</span>
          <div>
            我的實驗室<small>Local workspace</small>
          </div>
          <span className="version">v0.1</span>
        </div>
        <div className="nav-label">工作台</div>
        <nav>
          {[
            ["overview", LayoutDashboard, "評估總覽"],
            ["runs", Activity, "測試紀錄"],
            ["models", Layers3, "模型管理"],
            ["datasets", Database, "測試題庫"],
            ["prompts", TextCursorInput, "Prompt 版本"],
          ].map(([key, Icon, label]) => (
            <button
              key={key as string}
              className={
                page === key || (key === "runs" && page === "detail")
                  ? "nav active"
                  : "nav"
              }
              onClick={() => setPage(key as string)}
            >
              {typeof Icon !== "string" && <Icon size={19} />}
              <span>{label as string}</span>
              {key === "runs" && runs.length > 0 && <em>{runs.length}</em>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-status">
            <i className={online ? "connected" : ""} />
            {online ? "後端已連線" : "等待後端連線"}
          </div>
          <p>
            Build confidence.
            <br />
            One evaluation at a time.
          </p>
          <small>ModelBenchLab / 2026</small>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            工作台 <ChevronRight size={14} /> <span>{titles[page]}</span>
          </div>
          <div className="top-right">
            <span className="local-tag">
              <Terminal size={13} />
              本機工作區
            </span>
            <span className="avatar light">M</span>
          </div>
        </header>
        <div className="content">
          {error && (
            <div role="alert" className="alert error">
              <span>{error}</span>
              <button aria-label="關閉錯誤" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div role="status" className="alert success">
              <Check size={17} />
              {notice}
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {page === "detail"
                  ? "EXPERIMENT RESULTS"
                  : "MODEL EVALUATION / WORKSPACE"}
              </div>
              <h1>{page === "detail" ? detail?.name : titles[page]}</h1>
              <p>
                {
                  (
                    {
                      overview: "讓每一次模型選擇，都有實驗依據。",
                      runs: "追蹤每次實驗，保留可追溯的設定與結果。",
                      models: "連接雲端或本機模型，建立一致的測試入口。",
                      datasets: "以同一組題目，公平比較不同模型的表現。",
                      prompts: "保存每個提示詞版本，讓結果有跡可循。",
                      detail: "逐題檢視回答，從差異中找到下一步。",
                    } as Record<string, string>
                  )[page]
                }
              </p>
            </div>
            {["overview", "runs"].includes(page) && (
              <button className="primary" onClick={newRun} disabled={!online}>
                <Plus size={18} />
                建立測試
              </button>
            )}
            {page === "models" && (
              <button className="primary" onClick={() => setModal("model")}>
                <Plus size={18} />
                新增模型
              </button>
            )}
            {page === "datasets" && (
              <button className="primary" onClick={() => newDataset()}>
                <Plus size={18} />
                建立題庫
              </button>
            )}
            {page === "prompts" && (
              <button
                className="primary"
                onClick={() => {
                  setPromptForm({ name: "", text: "" });
                  setModal("prompt");
                }}
              >
                <Plus size={18} />
                新增版本
              </button>
            )}
          </div>
          {page === "overview" && (
            <>
              <div className="hero">
                <div>
                  <span className="hero-label">
                    <Sparkles size={14} /> YOUR NEXT EXPERIMENT
                  </span>
                  <h2>
                    同一道題，
                    <br />
                    看見模型之間的差異。
                  </h2>
                  <p>
                    從回答品質到回應速度，
                    <br />
                    在同一個工作台完成測試、評分與比較。
                  </p>
                  <button onClick={newRun} disabled={!online}>
                    開始模型比較 <ArrowRight size={17} />
                  </button>
                </div>
                <div className="hero-art" aria-hidden="true">
                  <div className="orbit" />
                  <div className="art-card first">
                    <span>
                      <i />
                      MODEL A
                    </span>
                    <div className="art-bar long" />
                    <div className="art-bar" />
                    <strong>
                      精確回應 <Check size={17} />
                    </strong>
                  </div>
                  <div className="art-card second">
                    <span>
                      <i />
                      MODEL B
                    </span>
                    <div className="art-bar long" />
                    <div className="art-bar" />
                    <strong>
                      多維度評估 <Activity size={17} />
                    </strong>
                  </div>
                  <span className="art-caption">
                    COMPARE. MEASURE. IMPROVE.
                  </span>
                </div>
              </div>
              <div className="stats">
                <div>
                  <span>
                    已連接模型
                    <Layers3 size={17} />
                  </span>
                  <strong>{models.length.toString().padStart(2, "0")}</strong>
                  <small>
                    包含 {models.filter((m) => m.provider === "demo").length}{" "}
                    個示範模型
                  </small>
                </div>
                <div>
                  <span>
                    測試題庫
                    <Database size={17} />
                  </span>
                  <strong>{datasets.length.toString().padStart(2, "0")}</strong>
                  <small>
                    共 {datasets.reduce((s, d) => s + d.cases.length, 0)}{" "}
                    道測試題目
                  </small>
                </div>
                <div>
                  <span>
                    累積測試
                    <Activity size={17} />
                  </span>
                  <strong>{runs.length.toString().padStart(2, "0")}</strong>
                  <small>
                    {runs.filter((r) => active(r.status)).length} 個測試執行中
                  </small>
                </div>
                <div>
                  <span>
                    規則通過率
                    <Check size={17} />
                  </span>
                  <strong>
                    {graded ? Math.round((passed / graded) * 100) + "%" : "—"}
                  </strong>
                  <small>僅計入有自動評分的回答</small>
                </div>
              </div>
              <section className="panel">
                <div className="section-head">
                  <h2>
                    最近的測試 <span>RECENT RUNS</span>
                  </h2>
                  <button
                    className="text-button"
                    onClick={() => setPage("runs")}
                  >
                    查看全部 <ArrowRight size={15} />
                  </button>
                </div>
                {runTable(runs.slice(0, 5))}
              </section>
              <div className="hint">
                <FlaskConical size={18} />
                <span>
                  示範模式提供固定回答與模擬延遲，僅用於熟悉流程，不代表真實模型能力。
                </span>
              </div>
            </>
          )}
          {page === "runs" && (
            <section className="panel">{runTable(runs)}</section>
          )}
          {page === "models" && (
            <>
              <div className="card-grid">
                {models.map((m) => (
                  <article className="model-card" key={m.id}>
                    <div className="card-top">
                      <span className="tile-icon">
                        <Layers3 size={22} />
                      </span>
                      <span className="pill neutral">
                        {m.provider === "demo" ? "DEMO" : "API"}
                      </span>
                    </div>
                    <h3>{m.name}</h3>
                    <code>{m.model}</code>
                    <p>
                      {m.provider === "demo"
                        ? "內建固定回答，無需金鑰，不產生 API 費用。"
                        : m.endpoint}
                    </p>
                    <div className="card-footer">
                      <small>
                        {m.has_key
                          ? "金鑰已加密保存"
                          : m.provider === "demo"
                            ? "本機示範"
                            : "未設定金鑰"}
                      </small>
                      <button
                        disabled={busy}
                        className="text-button"
                        onClick={() =>
                          action(async () => {
                            const r = await api<{ latency_ms: number }>(
                              "/models/" + m.id + "/test",
                              {},
                            );
                            setNotice("連線成功 · " + r.latency_ms + " ms");
                          })
                        }
                      >
                        測試連線 <ArrowRight size={14} />
                      </button>
                    </div>
                  </article>
                ))}
              </div>
              <div className="hint">
                <Settings2 size={18} />
                API 端點請填寫 base URL（例如
                http://localhost:11434/v1）。連線測試會發出一筆短請求。
              </div>
            </>
          )}
          {page === "datasets" && (
            <div className="card-grid">
              {datasets.map((d) => (
                <article className="model-card" key={d.id}>
                  <div className="card-top">
                    <span className="tile-icon">
                      <Database size={22} />
                    </span>
                    <span className="pill neutral">{d.cases.length} 題</span>
                  </div>
                  <h3>{d.name}</h3>
                  <p>
                    {d.cases
                      .slice(0, 3)
                      .map((c) => c.title)
                      .join(" · ")}
                    {d.cases.length > 3 ? "…" : ""}
                  </p>
                  <div className="card-footer">
                    <small>不可變更的題庫版本</small>
                    <button
                      className="text-button"
                      onClick={() => newDataset(d)}
                    >
                      檢視 / 複製編輯 <ArrowRight size={14} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
          {page === "prompts" && (
            <div className="card-grid">
              {prompts.map((p) => (
                <article className="model-card" key={p.id}>
                  <span className="tile-icon">
                    <TextCursorInput size={22} />
                  </span>
                  <h3>{p.name}</h3>
                  <pre className="prompt-text">{p.text}</pre>
                  <div className="card-footer">
                    <small>System Prompt</small>
                    <button
                      className="text-button"
                      onClick={() => {
                        setPromptForm({
                          name: p.name + " · 新版本",
                          text: p.text,
                        });
                        setModal("prompt");
                      }}
                    >
                      建立衍生版本 <ArrowRight size={14} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
          {page === "detail" && detail && (
            <>
              <div className="run-toolbar">
                <Badge status={detail.status} />
                <span>{detail.dataset_name}</span>
                <span>
                  {Object.entries(detail.counts)
                    .filter(([k]) => !["queued", "running"].includes(k))
                    .reduce((s, [, v]) => s + v, 0)}{" "}
                  / {detail.total} 完成
                </span>
                <div className="spacer" />
                <button
                  className="secondary"
                  onClick={() =>
                    action(async () => {
                      setDetail(await api("/runs/" + detail.id));
                      await refresh();
                    })
                  }
                >
                  <RefreshCw size={15} />
                  重新整理
                </button>
                {active(detail.status) ? (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      action(async () => {
                        await api("/runs/" + detail.id + "/cancel", {});
                        setDetail(await api("/runs/" + detail.id));
                        await refresh();
                      })
                    }
                  >
                    取消測試
                  </button>
                ) : (
                  !!detail.counts.failed && (
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        action(async () => {
                          const r = await api<{ id: string }>(
                            "/runs/" + detail.id + "/retry",
                            {},
                          );
                          await refresh();
                          setDetail(await api("/runs/" + r.id));
                        })
                      }
                    >
                      重跑失敗項目
                    </button>
                  )
                )}
                <a
                  className="secondary"
                  href={"/api/runs/" + detail.id + "/export?format=json"}
                >
                  <ArrowDownToLine size={15} />
                  JSON
                </a>
                <a
                  className="secondary"
                  href={"/api/runs/" + detail.id + "/export?format=csv"}
                >
                  CSV
                </a>
              </div>
              <div className="progress">
                <div
                  style={{
                    width:
                      ((detail.total -
                        (detail.counts.queued || 0) -
                        (detail.counts.running || 0)) /
                        Math.max(1, detail.total)) *
                        100 +
                      "%",
                  }}
                />
              </div>
              <div className="stats result-stats">
                {detail.models.map((m) => {
                  const items = detail.items.filter((i) => i.model_id === m.id);
                  const g = items.filter(
                    (i) => i.result?.evaluation.passed != null,
                  );
                  const p = g.filter((i) => i.result?.evaluation.passed);
                  const answered = items.filter((i) => i.result);
                  const latency = answered.length
                    ? Math.round(
                        answered.reduce((s, i) => s + i.result!.latency_ms, 0) /
                          answered.length,
                      )
                    : null;
                  return (
                    <div key={m.id}>
                      <span>{m.name}</span>
                      <strong>
                        {g.length
                          ? Math.round((p.length / g.length) * 100) + "%"
                          : "—"}
                      </strong>
                      <small>
                        {p.length}/{g.length} 規則通過 ·{" "}
                        {latency === null ? "—" : latency + " ms"} 平均延遲
                      </small>
                    </div>
                  );
                })}
              </div>
              <div className="section-head">
                <h2>
                  逐題比較 <span>SIDE BY SIDE</span>
                </h2>
                <select
                  aria-label="篩選結果"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="all">全部結果</option>
                  <option value="failed">未通過 / 執行失敗</option>
                  <option value="manual">待人工評分</option>
                </select>
              </div>
              {detail.snapshot.cases.map((c, idx) =>
                Array.from(
                  { length: detail.snapshot.settings.repeats },
                  (_, repeat) => {
                    const rows = detail.items.filter(
                      (i) => i.case_index === idx && i.repeat_index === repeat,
                    );
                    if (!rows.length) return null;
                    if (
                      filter === "failed" &&
                      !rows.some(
                        (i) =>
                          i.status === "failed" ||
                          i.result?.evaluation.passed === false,
                      )
                    )
                      return null;
                    if (
                      filter === "manual" &&
                      !rows.some(
                        (i) =>
                          i.result &&
                          i.result.evaluation.passed === null &&
                          !detail.reviews.some((r) => r.item_id === i.id),
                      )
                    )
                      return null;
                    return (
                      <section
                        className="case-result panel"
                        key={idx + "-" + repeat}
                      >
                        <div className="case-heading">
                          <span className="case-number">
                            {String(idx + 1).padStart(2, "0")}
                          </span>
                          <div>
                            <h3>
                              {c.title}
                              {detail.snapshot.settings.repeats > 1
                                ? " · 第 " + (repeat + 1) + " 次"
                                : ""}
                            </h3>
                            <p>{c.messages.at(-1)?.content}</p>
                          </div>
                          <span className="pill neutral">{c.rule.kind}</span>
                        </div>
                        {c.messages.length > 1 && (
                          <details>
                            <summary>完整對話</summary>
                            <pre>{JSON.stringify(c.messages, null, 2)}</pre>
                          </details>
                        )}
                        <div
                          className="answers"
                          style={{
                            gridTemplateColumns:
                              "repeat(" +
                              Math.min(2, detail.models.length) +
                              ", minmax(0, 1fr))",
                          }}
                        >
                          {detail.models.map((m) =>
                            answerCard(
                              rows.find((i) => i.model_id === m.id),
                              m,
                            ),
                          )}
                        </div>
                      </section>
                    );
                  },
                ),
              )}
            </>
          )}
          <footer>
            ModelBenchLab <span>可追溯的實驗 · 可比較的結果</span>
            <span className="footer-right">MVP / 0.1.0</span>
          </footer>
        </div>
      </main>
      {modal && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !busy) setModal(null);
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
            className={"modal " + (modal === "dataset" ? "wide" : "")}
          >
            <div className="modal-title">
              <div>
                <span className="eyebrow">MODEL BENCH LAB</span>
                <h2 id="modal-title">
                  {
                    (
                      {
                        run: "建立模型測試",
                        model: "連接新模型",
                        dataset: "建立題庫版本",
                        prompt: "建立 Prompt 版本",
                        review: "人工評分",
                      } as Record<string, string>
                    )[modal]
                  }
                </h2>
              </div>
              <button
                aria-label="關閉視窗"
                onClick={() => setModal(null)}
                disabled={busy}
              >
                <X />
              </button>
            </div>
            {error && <div className="alert error">{error}</div>}
            {modal === "run" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action(async () => {
                    const r = await api<Run>("/runs", runForm);
                    await refresh();
                    setDetail(await api("/runs/" + r.id));
                    setPage("detail");
                    setFilter("all");
                    setModal(null);
                  });
                }}
              >
                <label>
                  測試名稱
                  <input
                    required
                    value={runForm.name}
                    onChange={(e) =>
                      setRunForm({ ...runForm, name: e.target.value })
                    }
                  />
                </label>
                <div className="form-grid">
                  <label>
                    測試題庫
                    <select
                      required
                      value={runForm.dataset_id}
                      onChange={(e) =>
                        setRunForm({ ...runForm, dataset_id: e.target.value })
                      }
                    >
                      {datasets.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}（{d.cases.length} 題）
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Prompt 版本
                    <select
                      required
                      value={runForm.prompt_id}
                      onChange={(e) =>
                        setRunForm({ ...runForm, prompt_id: e.target.value })
                      }
                    >
                      {prompts.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <label>選擇模型</label>
                <div className="model-checks">
                  {models.map((m) => (
                    <label key={m.id}>
                      <input
                        type="checkbox"
                        checked={runForm.model_ids.includes(m.id)}
                        onChange={(e) =>
                          setRunForm({
                            ...runForm,
                            model_ids: e.target.checked
                              ? [...runForm.model_ids, m.id]
                              : runForm.model_ids.filter((x) => x !== m.id),
                          })
                        }
                      />
                      <span>
                        {m.name}
                        <small>
                          {m.provider === "demo" ? "示範模型 · 免費" : m.model}
                        </small>
                      </span>
                    </label>
                  ))}
                </div>
                <div className="form-grid">
                  <label>
                    重複次數
                    <input
                      type="number"
                      min="1"
                      max="5"
                      required
                      value={runForm.repeats}
                      onChange={(e) =>
                        setRunForm({
                          ...runForm,
                          repeats: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    Temperature
                    <input
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      required
                      value={runForm.temperature}
                      onChange={(e) =>
                        setRunForm({
                          ...runForm,
                          temperature: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    輸出 Token 上限
                    <input
                      type="number"
                      min="1"
                      max="8192"
                      required
                      value={runForm.max_tokens}
                      onChange={(e) =>
                        setRunForm({
                          ...runForm,
                          max_tokens: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    單次逾時（秒）
                    <input
                      type="number"
                      min="5"
                      max="180"
                      required
                      value={runForm.timeout}
                      onChange={(e) =>
                        setRunForm({
                          ...runForm,
                          timeout: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                </div>
                <div className="estimate">
                  <span>預計執行工作</span>
                  <strong>{requests} 次</strong>
                  <small>暫時性錯誤最多重試 2 次；真實模型依供應商計費。</small>
                </div>
                <button
                  className="primary full"
                  disabled={busy || !requests || requests > 5000}
                >
                  <Play size={16} />
                  {busy ? "正在建立…" : "開始測試"}
                </button>
              </form>
            )}
            {modal === "model" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action(async () => {
                    await api("/models", modelForm);
                    await refresh();
                    setModal(null);
                    setModelForm({
                      ...modelForm,
                      name: "",
                      model: "",
                      api_key: "",
                    });
                    setNotice("模型已新增，金鑰已加密保存");
                  });
                }}
              >
                <label>
                  顯示名稱
                  <input
                    required
                    placeholder="例如：Local / Qwen"
                    value={modelForm.name}
                    onChange={(e) =>
                      setModelForm({ ...modelForm, name: e.target.value })
                    }
                  />
                </label>
                <label>
                  API Base URL
                  <input
                    required
                    type="url"
                    value={modelForm.endpoint}
                    onChange={(e) =>
                      setModelForm({ ...modelForm, endpoint: e.target.value })
                    }
                  />
                </label>
                <label>
                  模型 ID
                  <input
                    required
                    placeholder="供應商的模型名稱"
                    value={modelForm.model}
                    onChange={(e) =>
                      setModelForm({ ...modelForm, model: e.target.value })
                    }
                  />
                </label>
                <label>
                  API Key <span className="muted">（本機服務可留空）</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={modelForm.api_key}
                    onChange={(e) =>
                      setModelForm({ ...modelForm, api_key: e.target.value })
                    }
                  />
                </label>
                <p className="form-note">
                  支援 OpenAI 相容的 chat/completions 文字介面。API Key
                  僅由後端保存及使用。
                </p>
                <button className="primary full" disabled={busy}>
                  儲存模型
                </button>
              </form>
            )}
            {modal === "prompt" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action(async () => {
                    await api("/prompts", promptForm);
                    await refresh();
                    setModal(null);
                    setNotice("新的 Prompt 版本已保存");
                  });
                }}
              >
                <label>
                  版本名稱
                  <input
                    required
                    value={promptForm.name}
                    onChange={(e) =>
                      setPromptForm({ ...promptForm, name: e.target.value })
                    }
                  />
                </label>
                <label>
                  System Prompt
                  <textarea
                    rows={7}
                    value={promptForm.text}
                    onChange={(e) =>
                      setPromptForm({ ...promptForm, text: e.target.value })
                    }
                  />
                </label>
                <p className="form-note">
                  建立後保留原始版本，後續修改請另存新版本。
                </p>
                <button className="primary full" disabled={busy}>
                  儲存版本
                </button>
              </form>
            )}
            {modal === "dataset" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action(async () => {
                    const parsed = jsonMode ? JSON.parse(caseJson) : cases;
                    await api("/datasets", {
                      name: datasetName,
                      cases: parsed,
                    });
                    await refresh();
                    setModal(null);
                    setNotice("題庫版本已保存");
                  });
                }}
              >
                <label>
                  題庫名稱
                  <input
                    required
                    value={datasetName}
                    onChange={(e) => setDatasetName(e.target.value)}
                  />
                </label>
                <div className="editor-toolbar">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      if (jsonMode) {
                        try {
                          const parsed = JSON.parse(caseJson);
                          if (
                            !Array.isArray(parsed) ||
                            !parsed.every(
                              (c) =>
                                typeof c.title === "string" &&
                                Array.isArray(c.messages) &&
                                c.messages.length &&
                                c.messages.every(
                                  (m: { content: unknown }) =>
                                    typeof m.content === "string",
                                ) &&
                                c.rule,
                            )
                          )
                            throw Error(
                              "請提供包含 title、messages 與 rule 的題目陣列",
                            );
                          setCases(parsed);
                          setJsonMode(false);
                        } catch (e) {
                          setError(String(e));
                        }
                      } else {
                        setCaseJson(JSON.stringify(cases, null, 2));
                        setJsonMode(true);
                      }
                    }}
                  >
                    {jsonMode ? "切換表單" : "編輯 JSON / 多輪對話"}
                  </button>
                  <label className="file-button">
                    匯入 JSON / CSV
                    <input
                      type="file"
                      accept=".json,.csv"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        action(async () => {
                          const text = await f.text();
                          let parsed: unknown;
                          if (f.name.endsWith(".csv")) {
                            const rows = parseCSV(text.replace(/^\uFEFF/, ""));
                            const headers = rows.shift() || [];
                            parsed = rows
                              .filter((r) => r.some(Boolean))
                              .map((r) => {
                                const row = Object.fromEntries(
                                  headers.map((h, i) => [h.trim(), r[i] || ""]),
                                );
                                return {
                                  title: row.title,
                                  messages: [
                                    { role: "user", content: row.question },
                                  ],
                                  rule: {
                                    kind: row.kind || "contains",
                                    expected: row.expected || "",
                                  },
                                };
                              });
                          } else {
                            const data = JSON.parse(text);
                            parsed = Array.isArray(data) ? data : data.cases;
                          }
                          if (!Array.isArray(parsed))
                            throw Error("檔案必須包含題目陣列");
                          setCaseJson(JSON.stringify(parsed, null, 2));
                          setJsonMode(true);
                          setNotice("匯入完成，請檢查內容後儲存");
                        });
                      }}
                    />
                  </label>
                </div>
                {jsonMode ? (
                  <label>
                    題目 JSON
                    <textarea
                      className="code-editor"
                      rows={14}
                      value={caseJson}
                      onChange={(e) => setCaseJson(e.target.value)}
                    />
                  </label>
                ) : (
                  <div className="case-editor-list">
                    {cases.map((c, i) => (
                      <div className="case-editor" key={i}>
                        <div className="case-editor-top">
                          <strong>題目 {i + 1}</strong>
                          <button
                            type="button"
                            aria-label={"刪除題目 " + (i + 1)}
                            disabled={cases.length === 1}
                            onClick={() =>
                              setCases(cases.filter((_, j) => i !== j))
                            }
                          >
                            <X size={16} />
                          </button>
                        </div>
                        <label>
                          標題
                          <input
                            required
                            value={c.title}
                            onChange={(e) =>
                              setCases(
                                cases.map((x, j) =>
                                  j === i ? { ...x, title: e.target.value } : x,
                                ),
                              )
                            }
                          />
                        </label>
                        <label>
                          問題
                          <textarea
                            required
                            rows={2}
                            value={c.messages.at(-1)?.content || ""}
                            onChange={(e) =>
                              setCases(
                                cases.map((x, j) =>
                                  j === i
                                    ? {
                                        ...x,
                                        messages: x.messages.map((m, k) =>
                                          k === x.messages.length - 1
                                            ? { ...m, content: e.target.value }
                                            : m,
                                        ),
                                      }
                                    : x,
                                ),
                              )
                            }
                          />
                        </label>
                        <div className="form-grid">
                          <label>
                            評分方式
                            <select
                              value={c.rule.kind}
                              onChange={(e) =>
                                setCases(
                                  cases.map((x, j) =>
                                    j === i
                                      ? {
                                          ...x,
                                          rule: {
                                            ...x.rule,
                                            kind: e.target
                                              .value as Case["rule"]["kind"],
                                          },
                                        }
                                      : x,
                                  ),
                                )
                              }
                            >
                              <option value="contains">包含文字</option>
                              <option value="exact">完全比對</option>
                              <option value="manual">人工評分</option>
                              <option value="json_schema">JSON Schema</option>
                            </select>
                          </label>
                          {["contains", "exact"].includes(c.rule.kind) && (
                            <label>
                              預期答案
                              <input
                                required
                                value={c.rule.expected || ""}
                                onChange={(e) =>
                                  setCases(
                                    cases.map((x, j) =>
                                      j === i
                                        ? {
                                            ...x,
                                            rule: {
                                              ...x.rule,
                                              expected: e.target.value,
                                            },
                                          }
                                        : x,
                                    ),
                                  )
                                }
                              />
                            </label>
                          )}
                        </div>
                        {c.rule.kind === "json_schema" && (
                          <p className="form-note">
                            請切換 JSON 編輯 rule.schema；目前：
                            {JSON.stringify(c.rule.schema || {})}
                          </p>
                        )}
                      </div>
                    ))}
                    <button
                      type="button"
                      className="secondary full"
                      onClick={() =>
                        setCases([
                          ...cases,
                          {
                            title: "新題目",
                            messages: [{ role: "user", content: "" }],
                            rule: { kind: "contains", expected: "" },
                          },
                        ])
                      }
                    >
                      <Plus size={16} />
                      新增題目
                    </button>
                  </div>
                )}
                <p className="form-note">
                  CSV 欄位：title, question, kind, expected。多輪對話與 JSON
                  Schema 請使用 JSON。儲存時會驗證格式。
                </p>
                <button className="primary full" disabled={busy}>
                  保存題庫版本
                </button>
              </form>
            )}
            {modal === "review" && reviewItem && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action(async () => {
                    await api("/items/" + reviewItem.id + "/review", {
                      score: reviewScore,
                      note: reviewNote,
                    });
                    setDetail(await api("/runs/" + detail!.id));
                    setModal(null);
                    setNotice("人工評分已記錄");
                  });
                }}
              >
                <label>
                  分數（1–5）
                  <select
                    value={reviewScore}
                    onChange={(e) => setReviewScore(Number(e.target.value))}
                  >
                    {[1, 2, 3, 4, 5].map((n) => (
                      <option key={n} value={n}>
                        {n} / 5
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  評分說明
                  <textarea
                    rows={4}
                    value={reviewNote}
                    onChange={(e) => setReviewNote(e.target.value)}
                  />
                </label>
                <p className="form-note">
                  人工評分獨立記錄，不會覆蓋自動規則的通過率。
                </p>
                <button className="primary full" disabled={busy}>
                  保存評分
                </button>
              </form>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function parseCSV(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      if (quoted && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else quoted = !quoted;
    } else if (ch === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((ch === "\n" || ch === "\r") && !quoted) {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else cell += ch;
  }
  if (quoted) throw Error("CSV 引號未閉合");
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}
