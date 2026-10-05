import { useEffect, useMemo, useState } from "react";
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
  TextCursorInput,
  Trash2,
  X,
} from "lucide-react";
import { api, Model, Dataset, Prompt, Run, Detail, Case, Item } from "./api";

import ModelManagement from "./features/models/ModelManagement";
import DatasetImport from "./features/datasets/DatasetImport";
import { parseDatasetFile } from "./features/datasets/parseDatasetFile";
import RankingChart from "./features/RankingChart";

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
const RESULT_PAGE_SIZE = 20;
type CaseGroup = { caseIndex: number; repeatIndex: number; case: Case; rows: Item[] };
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
  const [resultPage, setResultPage] = useState(1);
  const [expandedCase, setExpandedCase] = useState<string | null>(null);
  const [datasetName, setDatasetName] = useState("");
  const [deletingDataset, setDeletingDataset] = useState<Dataset | null>(null);
  const [deletingRun, setDeletingRun] = useState<Run | null>(null);
  const [forceCancellingRun, setForceCancellingRun] = useState<Run | null>(null);
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
    max_tokens: null as number | null,
    timeout: 600,
    code_timeout: 10,
  });
  const [batchConfirmed, setBatchConfirmed] = useState(false);
  useEffect(() => setBatchConfirmed(false), [runForm.dataset_id, runForm.model_ids, runForm.repeats, runForm.max_tokens]);
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
    const interval = runs.some((r) => r.batch_id && active(r.status)) ? 10000 : 2500;
    const t = setInterval(() => refresh().catch(() => {}), interval);
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
  useEffect(() => {
    setResultPage(1);
    setExpandedCase(null);
  }, [detail?.id]);
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
  function newRun(datasetChoice?: string) {
    setBatchConfirmed(false);
    setRunForm({
      name: "模型比較 · " + new Date().toLocaleDateString("zh-TW"),
      dataset_id: datasetChoice || (datasets[0]?.bundle_id ? `bundle:${datasets[0].bundle_id}` : datasets[0]?.id) || "",
      prompt_id: prompts[0]?.id || "",
      model_ids: models
        .filter((m) => m.provider === "demo" && m.available !== false)
        .map((m) => m.id),
      repeats: 1,
      temperature: 0,
      max_tokens: null,
      timeout: 600,
      code_timeout: 10,
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
  const selectedBundleId = runForm.dataset_id.startsWith("bundle:") ? runForm.dataset_id.slice(7) : null;
  const selectedDatasets = selectedBundleId
    ? datasets.filter((d) => d.bundle_id === selectedBundleId)
    : datasets.filter((d) => d.id === runForm.dataset_id);
  const requests =
    selectedDatasets.reduce((sum, d) => sum + (d.case_count ?? d.cases.length), 0) *
    runForm.model_ids.length *
    runForm.repeats;
  const selectedModels = models.filter((model) => runForm.model_ids.includes(model.id));
  const noTemperatureModels = selectedModels.filter(
    (model) => model.provider === "openrouter" && model.catalog &&
      !model.catalog.supported_parameters.includes("temperature"),
  );
  const noTokenLimitModels = selectedModels.filter(
    (model) => model.provider === "openrouter" && model.catalog &&
      !model.catalog.supported_parameters.includes("max_tokens"),
  );
  const overCatalogLimit = selectedModels.filter(
    (model) => model.catalog?.supported_parameters.includes("max_tokens") &&
      model.catalog.max_completion_tokens != null &&
      (runForm.max_tokens ?? model.max_output_tokens) > model.catalog.max_completion_tokens,
  );
  const datasetChoices = datasets.filter((d) => !d.bundle_id || d.bundle_index === 1);
  const deletingRunActive = deletingRun !== null && (
    active(deletingRun.status) ||
    (!!deletingRun.batch_id && runs.some((r) => r.batch_id === deletingRun.batch_id && active(r.status)))
  );
  const caseGroups = useMemo(() => {
    if (!detail) return [];
    const groups = new Map<string, CaseGroup>();
    for (const item of detail.items) {
      const sample = detail.snapshot.cases[item.case_index];
      if (!sample) continue;
      const key = `${item.case_index}-${item.repeat_index}`;
      let group = groups.get(key);
      if (!group) {
        group = { caseIndex: item.case_index, repeatIndex: item.repeat_index, case: sample, rows: [] };
        groups.set(key, group);
      }
      group.rows.push(item);
    }
    return [...groups.values()].sort((a, b) =>
      a.caseIndex - b.caseIndex || a.repeatIndex - b.repeatIndex,
    );
  }, [detail]);
  const filteredCaseGroups = useMemo(() => {
    if (filter === "all") return caseGroups;
    const reviewed = new Set(detail?.reviews.map((review) => review.item_id) ?? []);
    return caseGroups.filter(({ rows }) => {
      if (filter === "not-passed") {
        return rows.some((item) => item.result?.evaluation.passed === false);
      }
      if (filter === "failed") {
        return rows.some((item) => item.status === "failed");
      }
      if (filter === "evaluation-error") return rows.some(item => item.status === "completed" && item.result?.evaluation.error);
      return rows.some((item) =>
        item.status === "completed" && item.result?.evaluation.passed === null && !item.result.evaluation.error && !item.result.evaluation.pending && !reviewed.has(item.id),
      );
    });
  }, [caseGroups, detail?.reviews, filter]);
  const resultPageCount = Math.max(1, Math.ceil(filteredCaseGroups.length / RESULT_PAGE_SIZE));
  const visibleResultPage = Math.min(resultPage, resultPageCount);
  const visibleCaseGroups = filteredCaseGroups.slice(
    (visibleResultPage - 1) * RESULT_PAGE_SIZE,
    visibleResultPage * RESULT_PAGE_SIZE,
  );
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
              <th>已回報費用</th>
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
                <td className="run-cost-cell">
                  <strong>{r.models.every((model) => model.provider === "demo")
                    ? "示範"
                    : r.cost_summary?.reported_items
                      ? `$${r.cost_summary.reported_usd}`
                      : "尚無"}</strong>
                  {(r.cost_summary?.unknown_items ?? 0) > 0 && (
                    <small>{r.cost_summary.unknown_items} 題費用未明</small>
                  )}
                </td>
                <td className="muted">{formatTime(r.created_at)}</td>
                <td>
                  <div className="run-row-actions">
                    {page === "runs" && (
                      <button
                        type="button"
                        className="text-button run-delete-button"
                        aria-label={`刪除測試紀錄 ${r.name}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingRun(r);
                          setError("");
                          setModal("delete-run");
                        }}
                        onKeyDown={(e) => e.stopPropagation()}
                      >
                        <Trash2 size={15} /> 刪除
                      </button>
                    )}
                    <ChevronRight size={16} />
                  </div>
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
        <button className="primary" onClick={() => newRun()}>
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
    const lastAttempt = item.attempts.at(-1);
    const diagnostics = lastAttempt?.diagnostics;
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
              {item.status === "cancelled" ? "已取消" : ev?.passed === true
                ? "通過"
                : ev?.passed === false
                  ? "未通過"
                  : review
                    ? "人工已評"
                    : ev?.pending ? "正在評分" : ev?.error ? "評分失敗" : "待評分"}
            </span>
          ) : (
            <Badge status={item.status} />
          )}
        </div>
        <pre>
          {result?.output ||
            lastAttempt?.error ||
            (item.status === "queued"
              ? "等待 Worker 執行…"
              : item.status === "running"
                ? "正在生成回答…"
                : "尚無回答")}
        </pre>
        {!result && lastAttempt?.code === "no_text_output" && (
          <p className="reason">上游已有回應；這不是本工具判定的網路逾時。單靠空白回答與長度限制，無法確定推理 Token 是否用完。</p>
        )}
        {!result && diagnostics && Object.keys(diagnostics).length > 0 && (
          <details className="result-trace">
            <summary>檢視錯誤診斷</summary>
            <dl>
              {diagnostics.resolved_model && <><dt>實際模型</dt><dd>{diagnostics.resolved_model}</dd></>}
              {diagnostics.finish_reason && <><dt>結束原因</dt><dd>{diagnostics.finish_reason}</dd></>}
              {diagnostics.http_status != null && <><dt>HTTP 狀態</dt><dd>{diagnostics.http_status}</dd></>}
              {diagnostics.requested_max_tokens != null && <><dt>請求輸出上限</dt><dd>{diagnostics.requested_max_tokens.toLocaleString()} tokens</dd></>}
              {diagnostics.completion_tokens != null && <><dt>回報輸出用量</dt><dd>{diagnostics.completion_tokens.toLocaleString()} tokens</dd></>}
              {diagnostics.reasoning_tokens != null && <><dt>其中推理用量</dt><dd>{diagnostics.reasoning_tokens.toLocaleString()} tokens</dd></>}
              {diagnostics.timeout_kind && <><dt>逾時階段</dt><dd>{diagnostics.timeout_kind}</dd></>}
              {diagnostics.configured_timeout_seconds != null && <><dt>網路等待設定</dt><dd>{diagnostics.configured_timeout_seconds} 秒</dd></>}
              {diagnostics.elapsed_ms != null && <><dt>整體耗時</dt><dd>{(diagnostics.elapsed_ms / 1000).toFixed(1)} 秒</dd></>}
              {diagnostics.reported_cost_usd != null && <><dt>上游已回報費用</dt><dd>${diagnostics.reported_cost_usd}</dd></>}
            </dl>
          </details>
        )}
        {result && (
          <>
            <div className="answer-meta">
              <span>生成 {result.latency_ms} ms</span>
              {ev?.latency_ms != null && <span>程式評分 {(ev.latency_ms / 1000).toFixed(1)} 秒</span>}
              <span>
                {result.output_tokens === null
                  ? "Token 未提供"
                  : result.output_tokens + " output tokens"}
              </span>
              {result.demo ? (
                <span>示範資料</span>
              ) : (
                <span>
                  費用 {result.cost == null ? "未知" : "已回報 $" + result.cost}
                </span>
              )}
            </div>
            {!result.demo && (
              <details className="result-trace">
                <summary>檢視模型與路由資訊</summary>
                <dl>
                  <dt>請求模型</dt>
                  <dd>{result.requested_model || model.model}</dd>
                  <dt>回傳模型</dt>
                  <dd>{result.resolved_model || "上游未提供"}</dd>
                  <dt>服務商</dt>
                  <dd>{result.upstream_provider || "上游未提供"}</dd>
                  <dt>Generation</dt>
                  <dd>{result.generation_id || "上游未提供"}</dd>
                  <dt>金鑰版本</dt>
                  <dd>{result.credential_version ?? "未記錄"}</dd>
                </dl>
              </details>
            )}
            <div className="reason">
              {item.status === "cancelled" && ev?.pending ? "評分已取消；已保存的回答與費用保留" : review && ev?.passed === null
                ? "已記錄人工評分；不納入自動通過率"
                : ev?.reason}
            </div>
            {ev?.kind === "code" && <details className="result-trace">
              <summary>程式評分資訊與實際執行程式</summary>
              <dl><dt>結果類型</dt><dd>{ev.outcome || "等待評分"}</dd><dt>測試版本</dt><dd>{ev.tests_sha256 || "尚未執行"}</dd><dt>Python</dt><dd>{ev.runtime?.python || "未提供"}</dd><dt>評分器</dt><dd>{ev.runtime?.runner_version || "未提供"}</dd></dl>
              {ev.generated_code && <pre>{ev.generated_code}</pre>}
            </details>}
            {ev?.kind === "tool_call" && <details className="result-trace">
              <summary>工具調用評分資訊</summary>
              <dl><dt>類別</dt><dd>{ev.category}</dd><dt>評分版本</dt><dd>{ev.version}</dd><dt>錯誤類型</dt><dd>{ev.error_type || "無"}</dd></dl>
              <pre>{JSON.stringify(ev.calls || result?.tool_calls || [], null, 2)}</pre>
            </details>}
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
              {(ev?.error || ev?.kind === "code" || ev?.kind === "tool_call") && item.status === "completed" && !ev?.pending && detail && ["completed", "completed_with_errors"].includes(detail.status) && (
                <button
                  className="text-button"
                  onClick={() =>
                    action(async () => {
                      await api("/items/" + item.id + "/evaluate", {});
                      setDetail(await api("/runs/" + detail!.id));
                    })
                  }
                >
                  重新評分（不重新生成）
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
          <span className="version">v0.2</span>
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
          <small>ModelBenchLab / 2026</small>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            工作台 <ChevronRight size={14} /> <span>{titles[page]}</span>
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
              <button className="primary" onClick={() => newRun()} disabled={!online}>
                <Plus size={18} />
                建立測試
              </button>
            )}

            {page === "datasets" && (
              <div className="heading-actions">
                <button className="secondary" onClick={() => { setError(""); setModal("import"); }}>
                  <Database size={17} />
                  匯入
                </button>
                <button className="primary" onClick={() => newDataset()}>
                  <Plus size={18} />
                  建立題庫
                </button>
              </div>
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
              <div className="stats overview-stats">
                <div>
                  <span>
                    已連接模型
                    <Layers3 size={17} />
                  </span>
                  <strong>{models.length.toString().padStart(2, "0")}</strong>
                  <small>
                    包含{" "}
                    {
                      models.filter(
                        (m) => m.provider === "demo" && m.available !== false,
                      ).length
                    }{" "}
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
                    共 {datasets.reduce((s, d) => s + (d.case_count ?? d.cases.length), 0)}{" "}
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
              <RankingChart
                runs={runs}
                onNewRun={() => newRun()}
              />
            </>
          )}
          {page === "runs" && (
            <section className="panel">{runTable(runs)}</section>
          )}
          {page === "models" && (
            <ModelManagement models={models} onRefresh={refresh} />
          )}
          {page === "datasets" && (
            <div className="card-grid">
              {datasetChoices.length === 0 && (
                <div className="empty">目前沒有可用題庫。可建立新題庫，或從 Hugging Face／本機檔案匯入。</div>
              )}
              {datasetChoices.map((d) => (
                <article className="model-card" key={d.id}>
                  <div className="card-top">
                    <span className="tile-icon">
                      <Database size={22} />
                    </span>
                    <span className="pill neutral">{d.bundle_id
                      ? datasets.filter((part) => part.bundle_id === d.bundle_id).reduce((sum, part) => sum + (part.case_count ?? part.cases.length), 0)
                      : d.case_count ?? d.cases.length} 題</span>
                  </div>
                  <h3>{d.bundle_name || d.name}</h3>
                  <p>
                    {d.bundle_id
                      ? `分批題庫 · ${d.bundle_total} 批 · 建立測試時一次送出`
                      : <>{d.cases.slice(0, 3).map((c) => c.title).join(" · ")}{d.cases.length > 3 ? "…" : ""}</>}
                  </p>
                  <div className="card-footer">
                    <small>不可變更的題庫版本</small>
                    <div className="dataset-card-actions">
                      <button
                        className="text-button"
                        onClick={() => d.bundle_id ? newRun(`bundle:${d.bundle_id}`) : (d.coding || d.tool_call) ? newRun(d.id) : newDataset(d)}
                      >
                        {d.bundle_id ? "建立整批測試" : d.tool_call ? "建立工具調用測試" : d.coding ? "建立程式測試" : "檢視 / 複製編輯"} <ArrowRight size={14} />
                      </button>
                      <button
                        className="text-button dataset-delete-button"
                        aria-label={`刪除題庫 ${d.bundle_name || d.name}`}
                        onClick={() => {
                          setDeletingDataset(d);
                          setError("");
                          setModal("delete-dataset");
                        }}
                      >
                        <Trash2 size={14} /> 刪除
                      </button>
                    </div>
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
                  <>
                    {detail.status !== "cancelling" && (
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
                    )}
                    <button
                      className="secondary run-delete-button"
                      disabled={busy}
                      onClick={() => {
                        setForceCancellingRun(detail);
                        setError("");
                        setModal("force-cancel");
                      }}
                    >
                      強制取消
                    </button>
                  </>
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
                <button
                  type="button"
                  className="secondary run-delete-button"
                  onClick={() => {
                    setDeletingRun(detail);
                    setError("");
                    setModal("delete-run");
                  }}
                >
                  <Trash2 size={15} /> 刪除
                </button>
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
              {detail.models.some((model) => model.provider !== "demo") && (
                <div className="run-cost-panel panel" aria-label="測試費用">
                  <div>
                    <span>目前已回報費用</span>
                    <strong>{detail.cost_summary?.reported_items
                      ? `$${detail.cost_summary.reported_usd}`
                      : "尚無"}</strong>
                    <small>{detail.cost_summary?.reported_items ?? 0} 題已回報實際費用</small>
                  </div>
                  <p>
                    每完成一題即更新。OpenRouter 使用回應中的實際費用；
                    {detail.cost_summary?.unknown_items
                      ? `${detail.cost_summary.unknown_items} 題費用未明，包含未回報或失敗的請求。`
                      : "目前沒有費用未明的已結束請求。"}
                    此金額不含尚在執行中的請求。
                  </p>
                </div>
              )}
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
                      {m.provider !== "demo" && (
                        <small>
                          已回報費用 {detail.cost_summary?.by_model[m.id]?.reported_items
                            ? `$${detail.cost_summary.by_model[m.id].reported_usd}`
                            : "尚無"}
                          {detail.cost_summary?.by_model[m.id]?.unknown_items
                            ? ` · ${detail.cost_summary.by_model[m.id].unknown_items} 題費用未明`
                            : ""}
                        </small>
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="section-head" id="case-results">
                <h2>
                  逐題比較 <span>SIDE BY SIDE</span>
                </h2>
                <select
                  aria-label="篩選結果"
                  value={filter}
                  onChange={(e) => {
                    setFilter(e.target.value);
                    setResultPage(1);
                    setExpandedCase(null);
                  }}
                >
                  <option value="all">全部結果</option>
                  <option value="not-passed">未通過</option>
                  <option value="failed">執行失敗</option>
                  <option value="evaluation-error">評分失敗</option>
                  <option value="manual">待人工評分</option>
                </select>
              </div>
              <p className="result-list-meta" aria-live="polite">
                {filteredCaseGroups.length
                  ? `共 ${filteredCaseGroups.length} 題，顯示第 ${(visibleResultPage - 1) * RESULT_PAGE_SIZE + 1}–${Math.min(visibleResultPage * RESULT_PAGE_SIZE, filteredCaseGroups.length)} 題；點選題目查看回答。`
                  : "沒有符合條件的題目。"}
              </p>
              {visibleCaseGroups.map(({ caseIndex, repeatIndex, case: sample, rows }) => {
                const key = `${caseIndex}-${repeatIndex}`;
                const expanded = expandedCase === key;
                const prompt = sample.messages.at(-1)?.content ?? "";
                const executionFailed = rows.some((item) => item.status === "failed");
                const notPassed = rows.some((item) => item.result?.evaluation.passed === false);
                const evaluationError = rows.some(item => item.status === "completed" && item.result?.evaluation.error);
                const pending = rows.some((item) => active(item.status));
                const cancelled = rows.every((item) => item.status === "cancelled");
                const passed = rows.every((item) => item.result?.evaluation.passed === true);
                const statusText = executionFailed && notPassed
                  ? "未通過／執行失敗"
                  : executionFailed
                    ? "執行失敗"
                    : notPassed
                      ? "未通過"
                      : pending ? (rows.some(item => item.result?.evaluation.pending) ? "程式評分中" : "執行中") : cancelled ? "已取消" : evaluationError ? "評分失敗" : passed ? "通過" : "已回答／待評";
                return (
                  <section className="case-result panel" key={key}>
                    <button
                      type="button"
                      className="case-heading case-toggle"
                      aria-expanded={expanded}
                      onClick={() => setExpandedCase(expanded ? null : key)}
                    >
                      <span className="case-number">{String(caseIndex + 1).padStart(2, "0")}</span>
                      <div>
                        <h3>
                          {sample.title}
                          {detail.snapshot.settings.repeats > 1
                            ? " · 第 " + (repeatIndex + 1) + " 次"
                            : ""}
                        </h3>
                        <p>{expanded || prompt.length <= 180 ? prompt : `${prompt.slice(0, 180)}…`}</p>
                      </div>
                      <span className={"pill " + (executionFailed || notPassed ? "bad" : passed ? "good" : "neutral")}>{statusText}</span>
                      <ChevronRight className={expanded ? "case-chevron expanded" : "case-chevron"} size={16} />
                    </button>
                    {expanded && (
                      <>
                        {sample.messages.length > 1 && (
                          <details>
                            <summary>完整對話</summary>
                            <pre>{JSON.stringify(sample.messages, null, 2)}</pre>
                          </details>
                        )}
                        <div
                          className="answers"
                          style={{ gridTemplateColumns: `repeat(${Math.min(2, detail.models.length)}, minmax(0, 1fr))` }}
                        >
                          {detail.models.map((model) =>
                            answerCard(rows.find((item) => item.model_id === model.id), model),
                          )}
                        </div>
                      </>
                    )}
                  </section>
                );
              })}
              {resultPageCount > 1 && (
                <nav className="result-pagination" aria-label="結果分頁">
                  <button className="secondary" disabled={visibleResultPage === 1} onClick={() => {
                    setResultPage(visibleResultPage - 1);
                    setExpandedCase(null);
                    document.getElementById("case-results")?.scrollIntoView();
                  }}>上一頁</button>
                  <select aria-label="選擇結果頁" value={visibleResultPage} onChange={(event) => {
                    setResultPage(Number(event.target.value));
                    setExpandedCase(null);
                    document.getElementById("case-results")?.scrollIntoView();
                  }}>
                    {Array.from({ length: resultPageCount }, (_, index) => (
                      <option key={index + 1} value={index + 1}>第 {index + 1} / {resultPageCount} 頁</option>
                    ))}
                  </select>
                  <button className="secondary" disabled={visibleResultPage === resultPageCount} onClick={() => {
                    setResultPage(visibleResultPage + 1);
                    setExpandedCase(null);
                    document.getElementById("case-results")?.scrollIntoView();
                  }}>下一頁</button>
                </nav>
              )}
            </>
          )}
          <footer>
            ModelBenchLab <span>可追溯的實驗 · 可比較的結果</span>
            <span className="footer-right">MVP / 0.2.0</span>
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
            className={"modal " + (["dataset", "import"].includes(modal) ? "wide" : "")}
          >
            <div className="modal-title">
              <div>
                <span className="eyebrow">MODEL BENCH LAB</span>
                <h2 id="modal-title">
                  {
                    (
                      {
                        run: "建立模型測試",
                        dataset: "建立題庫版本",
                        "delete-dataset": "刪除測試題庫",
                        "delete-run": "刪除測試紀錄",
                        "force-cancel": "強制取消測試",
                        import: "匯入題庫",
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
            {modal === "force-cancel" && forceCancellingRun && (
              <div className="run-delete-confirm">
                <p>確定要立即結束「{forceCancellingRun.name}」嗎？</p>
                <p>
                  {forceCancellingRun.batch_id && "同一批次的所有分段會一起取消。"}
                  排隊及執行中的題目會立即標為取消，晚到的回答不會儲存。已送出的請求仍可能在廠商端執行並計費，費用也可能無法取得。
                  本機正在執行的程式評分容器也會停止；已保存的模型回答與費用保留。
                </p>
                <div className="dataset-delete-actions">
                  <button type="button" className="secondary" disabled={busy} onClick={() => setModal(null)}>返回</button>
                  <button type="button" className="primary dataset-danger-fill" disabled={busy} onClick={() => action(async () => {
                    await api(`/runs/${forceCancellingRun.id}/force-cancel`, {});
                    setModal(null);
                    setForceCancellingRun(null);
                    setDetail(await api<Detail>(`/runs/${forceCancellingRun.id}`));
                    await refresh();
                    setNotice("測試已強制取消，晚到的回答不會覆寫結果");
                  })}>
                    {busy ? "取消中…" : "確認強制取消"}
                  </button>
                </div>
              </div>
            )}
            {modal === "delete-run" && deletingRun && (
              <div className="run-delete-confirm">
                <p>確定要刪除「{deletingRun.name}」嗎？</p>
                <p>
                  {deletingRun.batch_id && "同一批次的所有測試紀錄會一併移除。"}
                  刪除後無法在介面檢視或匯出這些結果；資料仍保留於本機資料庫。
                </p>
                {deletingRunActive && <p>測試尚未停止。請先取消測試，等待所有工作停止後再刪除。</p>}
                <div className="dataset-delete-actions">
                  <button type="button" className="secondary" disabled={busy} onClick={() => setModal(null)}>取消</button>
                  <button type="button" className="primary dataset-danger-fill" disabled={busy || deletingRunActive} onClick={() => action(async () => {
                    await api(`/runs/${deletingRun.id}`, undefined, "DELETE");
                    setModal(null);
                    setDeletingRun(null);
                    setDetail(null);
                    setPage("runs");
                    await refresh();
                    setNotice("測試紀錄已移除");
                  })}>
                    {busy ? "刪除中…" : "確認刪除"}
                  </button>
                </div>
              </div>
            )}
            {modal === "delete-dataset" && deletingDataset && (
              <div className="dataset-delete-confirm">
                <p>確定要刪除「{deletingDataset.bundle_name || deletingDataset.name}」嗎？</p>
                <p>
                  {deletingDataset.bundle_id
                    ? `這組題庫的 ${deletingDataset.bundle_total} 個批次會一併從可用清單移除。`
                    : "此題庫會從可用清單移除。"}
                  之後無法用它建立新測試；既有測試紀錄與結果仍會保留。
                </p>
                <div className="dataset-delete-actions">
                  <button type="button" className="secondary" disabled={busy} onClick={() => setModal(null)}>取消</button>
                  <button type="button" className="primary dataset-danger-fill" disabled={busy} onClick={() => action(async () => {
                    await api(`/datasets/${deletingDataset.id}`, undefined, "DELETE");
                    setModal(null);
                    setDeletingDataset(null);
                    await refresh();
                    setNotice("題庫已從可用清單移除");
                  })}>
                    {busy ? "刪除中…" : "確認刪除"}
                  </button>
                </div>
              </div>
            )}
            {modal === "import" && (
              <DatasetImport
                onSaved={() => {
                  setModal(null);
                  setNotice("題庫已加入，可用於建立測試");
                  refresh().catch((e) => setError(e instanceof Error ? e.message : "無法更新題庫清單"));
                }}
                onLocalFile={(file, importedCases) => {
                  setDatasetName(file.name.replace(/\.(json|csv)$/i, ""));
                  setCases(importedCases);
                  setCaseJson(JSON.stringify(importedCases, null, 2));
                  setJsonMode(true);
                  setError("");
                  setModal("dataset");
                }}
              />
            )}
            {modal === "run" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action(async () => {
                    if (selectedBundleId) {
                      const result = await api<{ runs: number; jobs: number }>("/run-batches", {
                        ...runForm, dataset_id: undefined, bundle_id: selectedBundleId,
                      });
                      await refresh();
                      setPage("runs");
                      setModal(null);
                      setNotice(`已建立 ${result.runs} 批測試，共 ${result.jobs} 個工作項目`);
                      return;
                    }
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
                      onChange={(e) => {
                        setRunForm({ ...runForm, dataset_id: e.target.value });
                        setBatchConfirmed(false);
                      }}
                    >
                      {datasetChoices.map((d) => (
                        <option key={d.id} value={d.bundle_id ? `bundle:${d.bundle_id}` : d.id}>
                          {d.bundle_name || d.name}（{d.bundle_id
                            ? datasets.filter((part) => part.bundle_id === d.bundle_id).reduce((sum, part) => sum + (part.case_count ?? part.cases.length), 0)
                            : d.case_count ?? d.cases.length} 題）
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
                        disabled={m.available === false}
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
                          {m.available === false
                            ? m.unavailable_reason
                            : m.provider === "demo"
                              ? "示範模型 · 免費"
                              : m.model}
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
                    {noTemperatureModels.length > 0 && (
                      <small>這些模型未宣告支援 Temperature，請求會略過此設定：{noTemperatureModels.map((model) => model.name).join("、")}</small>
                    )}
                  </label>
                  <label>
                    覆寫輸出 Token 上限（選填）
                    <input
                      type="number"
                      min="1"
                      max="131072"
                      step="1"
                      placeholder="留空時依各模型設定"
                      value={runForm.max_tokens ?? ""}
                      onChange={(e) =>
                        setRunForm({
                          ...runForm,
                          max_tokens: e.target.value === "" ? null : Number(e.target.value),
                        })
                      }
                    />
                    <small>留空時使用各模型的輸出上限（新模型預設 128,000）；填寫後套用至本次所有模型。上限含可能的推理 token，實際費用依用量計。</small>
                    {noTokenLimitModels.length > 0 && (
                      <small>這些模型未宣告支援 max_tokens，請求會略過此上限：{noTokenLimitModels.map((model) => model.name).join("、")}</small>
                    )}
                    {selectedModels.length > 0 && runForm.max_tokens === null && (
                      <small>目前模型設定：{selectedModels.map((model) => `${model.name} ${model.max_output_tokens.toLocaleString()}`).join("、")}</small>
                    )}
                    {overCatalogLimit.length > 0 && (
                      <small role="alert">超過目錄宣告上限：{overCatalogLimit.map((model) => `${model.name} ${model.catalog?.max_completion_tokens?.toLocaleString()}`).join("、")}；請調低模型設定或填入較低的本次覆寫值。</small>
                    )}
                  </label>
                  <label>
                    網路等待逾時（秒）
                    <input
                      type="number"
                      min="5"
                      max="600"
                      required
                      value={runForm.timeout}
                      onChange={(e) =>
                        setRunForm({
                          ...runForm,
                          timeout: Number(e.target.value),
                        })
                      }
                    />
                    <small>這是單次連線或讀寫等待的上限，不是整題總耗時上限；總耗時可能超過此值。</small>
                  </label>
                  <label>程式執行時間上限（秒）
                    <input type="number" min="1" max="120" required value={runForm.code_timeout} onChange={e => setRunForm({ ...runForm, code_timeout: Number(e.target.value) })} />
                    <small>僅用於 HumanEval／HumanEval+；每題生成一次，使用隔離 Python 評分器。此值與網路等待分開。</small>
                  </label>
                </div>
                <div className="estimate">
                  <span>預計執行工作</span>
                  <strong>{requests} 次</strong>
                  <small>
                    限流或服務暫時異常最多重試 2
                    次；逾時不自動重送。真實模型依供應商計費。
                  </small>
                  {selectedBundleId && <small>
                    系統會將題目分批成每次最多 5,000 個工作項目；整批上限 50,000 次。
                  </small>}
                  {requests > (selectedBundleId ? 50000 : 5000) && <small role="alert">
                    超過測試上限，請減少模型或重複次數。
                  </small>}
                </div>
                {selectedBundleId && <label className="batch-confirm">
                  <input type="checkbox" checked={batchConfirmed} onChange={(e) => setBatchConfirmed(e.target.checked)} />
                  我已確認 {requests} 次模型請求可能產生費用，並要一次送出全部批次。
                </label>}
                <button
                  className="primary full"
                  disabled={busy || !requests || requests > (selectedBundleId ? 50000 : 5000) || (selectedBundleId !== null && !batchConfirmed)}
                >
                  <Play size={16} />
                  {busy ? "正在建立…" : "開始測試"}
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
                          const parsed = await parseDatasetFile(f);
                          setCaseJson(JSON.stringify(parsed, null, 2));
                          setCases(parsed);
                          setJsonMode(true);
                          setNotice("匯入完成，請檢查內容後儲存");
                        });
                        e.target.value = "";
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
                              <option value="choice">選擇題答案</option>
                              <option value="manual">人工評分</option>
                              <option value="json_schema">JSON Schema</option>
                            </select>
                          </label>
                          {["contains", "exact", "choice"].includes(c.rule.kind) && (
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
