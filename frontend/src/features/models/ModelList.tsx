import { useState } from "react";
import { Plus, Search, Trash2, X } from "lucide-react";
import { api, type Connection, type Model, type ProviderType, type ReasoningEffort } from "../../api";
import { catalogPrice, modelStatus, providerFor } from "./modelUi";
import ReasoningEffortField from "./ReasoningEffortField";
import OutputTokensField, { validOutputTokens } from "./OutputTokensField";
import { useDialogFocus } from "./useDialogFocus";

export default function ModelList({
  models,
  connections,
  types,
  busy,
  highlightId,
  onAdd,
  onTrial,
  onToggle,
  onDelete,
  onConnection,
  onRefresh,
}: {
  models: Model[];
  connections: Connection[];
  types: ProviderType[];
  busy: boolean;
  highlightId: string;
  onAdd: (connectionId?: string) => void;
  onTrial: (model: Model) => void;
  onToggle: (model: Model) => void;
  onDelete: (model: Model) => void;
  onConnection: (id: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [detailId, setDetailId] = useState("");
  const [effortDraft, setEffortDraft] = useState<ReasoningEffort | "">("");
  const [outputTokensDraft, setOutputTokensDraft] = useState("32768");
  const [effortSaving, setEffortSaving] = useState(false);
  const [effortError, setEffortError] = useState("");
  const [effortNotice, setEffortNotice] = useState("");
  const dialogRef = useDialogFocus<HTMLElement>(Boolean(detailId), () =>
    setDetailId(""),
  );
  const detail = models.find((model) => model.id === detailId);
  function openDetail(model: Model) {
    setDetailId(model.id);
    setEffortDraft(model.reasoning_effort || "");
    setOutputTokensDraft(String(model.max_output_tokens));
    setEffortError("");
    setEffortNotice("");
  }

  async function saveSettings(model: Model) {
    if (effortSaving || !validOutputTokens(outputTokensDraft)) return;
    setEffortSaving(true);
    setEffortError("");
    setEffortNotice("");
    try {
      await api(`/models/${model.id}`, {
        reasoning_effort: effortDraft || null,
        max_output_tokens: Number(outputTokensDraft),
      }, "PATCH");
      await onRefresh();
      setEffortNotice("模型設定已保存；下次試跑與新測試將使用此設定。");
    } catch (cause) {
      setEffortError(cause instanceof Error ? cause.message : "無法保存模型設定");
    } finally {
      setEffortSaving(false);
    }
  }
  const connectionFor = (model: Model) =>
    connections.find((connection) => connection.id === model.connection_id);
  const stateFor = (model: Model) => {
    const connection = connectionFor(model);
    return modelStatus(model, connection, providerFor(types, model.provider));
  };
  const filtered = models.filter((model) => {
    const connection = connectionFor(model);
    const status = stateFor(model);
    const matchesSearch = (model.name + " " + model.model)
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase());
    const matchesSource =
      source === "all" ||
      (source === "demo"
        ? model.provider === "demo"
        : model.connection_id === source);
    const matchesStatus =
      statusFilter === "all" ||
      (statusFilter === "ready"
        ? status.tone === "ready"
        : statusFilter === "disabled"
          ? model.enabled === false
          : status.tone === "warning" && model.enabled !== false);
    return (
      matchesSearch &&
      matchesSource &&
      matchesStatus &&
      (source !== "demo" || !connection)
    );
  });

  return (
    <section className="mm-workspace" aria-label="我的模型">
      <div className="mm-toolbar">
        <div>
          <h2>
            我的模型 <span className="mm-count">{models.length}</span>
          </h2>
          <p>搜尋、試跑與管理已加入的模型。</p>
        </div>
        <button className="primary" onClick={() => onAdd()}>
          <Plus size={16} />
          加入模型
        </button>
      </div>
      {models.length > 0 && (
        <div className="mm-filters" aria-label="模型篩選">
          <label className="mm-search">
            <Search size={16} aria-hidden="true" />
            <span className="sr-only">搜尋模型名稱或 ID</span>
            <input
              type="search"
              placeholder="搜尋模型名稱或 ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label>
            <span className="sr-only">篩選連線</span>
            <select
              value={source}
              onChange={(event) => setSource(event.target.value)}
            >
              <option value="all">所有來源</option>
              <option value="demo">本機示範</option>
              {connections.map((connection) => (
                <option key={connection.id} value={connection.id}>
                  {connection.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="sr-only">篩選狀態</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="all">所有狀態</option>
              <option value="ready">可試跑</option>
              <option value="attention">需要處理</option>
              <option value="disabled">模型已停用</option>
            </select>
          </label>
        </div>
      )}
      {!models.length ? (
        <div className="mm-empty">
          <h3>還沒有模型</h3>
          <p>先加入模型；可以選現有連線，或在流程中建立新連線。</p>
          <button className="primary" onClick={() => onAdd()}>
            加入第一個模型
          </button>
        </div>
      ) : !filtered.length ? (
        <div className="mm-empty">
          <h3>沒有符合條件的模型</h3>
          <p>試試其他名稱、來源或狀態。</p>
          <button
            className="secondary"
            onClick={() => {
              setSearch("");
              setSource("all");
              setStatusFilter("all");
            }}
          >
            清除篩選
          </button>
        </div>
      ) : (
        <div className="panel table-wrap mm-model-table-wrap">
          <table className="mm-model-table">
            <thead>
              <tr>
                <th>模型</th>
                <th>連線</th>
                <th>狀態</th>
                <th>目錄資訊</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((model) => {
                const connection = connectionFor(model);
                const status = stateFor(model);
                return (
                  <tr
                    key={model.id}
                    className={highlightId === model.id ? "mm-highlight" : ""}
                  >
                    <td data-label="模型">
                      <strong>{model.name}</strong>
                      <code>{model.model}</code>
                    </td>
                    <td data-label="連線">
                      <span>
                        {connection?.name ||
                          (model.provider === "demo"
                            ? "本機示範"
                            : model.connection_name || "自訂端點")}
                      </span>
                      <small>
                        {model.provider === "demo"
                          ? "Demo"
                          : providerFor(types, model.provider)?.label ||
                            model.provider}
                      </small>
                    </td>
                    <td data-label="狀態">
                      <span className={`mm-status ${status.tone}`}>
                        {status.label}
                      </span>
                    </td>
                    <td data-label="目錄資訊">
                      {model.catalog?.context_length
                        ? `${model.catalog.context_length.toLocaleString()} Context`
                        : "—"}
                    </td>
                    <td data-label="操作" className="mm-row-actions">
                      <button
                        className="secondary"
                        onClick={() => openDetail(model)}
                      >
                        詳情
                      </button>
                      <button
                        className="primary"
                        disabled={busy || status.tone !== "ready"}
                        onClick={() => onTrial(model)}
                      >
                        試跑
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {detail &&
        (() => {
          const connection = connectionFor(detail);
          const status = stateFor(detail);
          return (
            <div
              className="mm-drawer-backdrop"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) setDetailId("");
              }}
            >
              <aside
                ref={dialogRef}
                className="mm-drawer"
                role="dialog"
                aria-modal="true"
                aria-labelledby="mm-model-detail-title"
              >
                <div className="mm-drawer-head">
                  <div>
                    <small>模型詳情</small>
                    <h2 id="mm-model-detail-title">{detail.name}</h2>
                  </div>
                  <button
                    className="mm-icon-button"
                    aria-label="關閉模型詳情"
                    onClick={() => setDetailId("")}
                  >
                    <X size={20} />
                  </button>
                </div>
                <div className="mm-drawer-body">
                  <span className={`mm-status ${status.tone}`}>
                    {status.label}
                  </span>
                  {status.detail && (
                    <p className="mm-status-help">{status.detail}</p>
                  )}
                  <dl className="mm-detail-list">
                    <dt>模型 ID</dt>
                    <dd>
                      <code>{detail.model}</code>
                    </dd>
                    <dt>服務類型</dt>
                    <dd>
                      {detail.provider === "demo"
                        ? "本機示範"
                        : providerFor(types, detail.provider)?.label ||
                          detail.provider}
                    </dd>
                    <dt>所屬連線</dt>
                    <dd>{connection?.name || detail.connection_name || "—"}</dd>
                    <dt>思考程度</dt>
                    <dd>{detail.reasoning_effort || "模型預設"}</dd>
                    <dt>輸出 Token 上限</dt>
                    <dd>{detail.max_output_tokens.toLocaleString()}</dd>
                  </dl>
                  {detail.provider !== "demo" && (
                    <div className="mm-reasoning-editor">
                      <ReasoningEffortField
                        value={effortDraft}
                        onChange={(value) => {
                          setEffortDraft(value);
                          setEffortError("");
                          setEffortNotice("");
                        }}
                        disabled={effortSaving || busy}
                      />
                      <OutputTokensField
                        value={outputTokensDraft}
                        onChange={(value) => {
                          setOutputTokensDraft(value);
                          setEffortError("");
                          setEffortNotice("");
                        }}
                        disabled={effortSaving || busy}
                      />
                      <button
                        className="secondary"
                        disabled={
                          effortSaving ||
                          busy ||
                          !validOutputTokens(outputTokensDraft) ||
                          (effortDraft === (detail.reasoning_effort || "") &&
                            Number(outputTokensDraft) === detail.max_output_tokens)
                        }
                        onClick={() => saveSettings(detail)}
                      >
                        {effortSaving ? "保存中…" : "保存模型設定"}
                      </button>
                      <p className="mm-form-help">
                        輸出上限含可能使用的推理 token；這是上限，不代表每次都會用完。模型或服務商若不支援，請求可能失敗。
                      </p>
                      {detail.catalog && !detail.catalog.supported_parameters.includes("max_tokens") && (
                        <p className="mm-form-help">此模型未宣告支援 max_tokens；試跑與正式測試會略過輸出上限設定。</p>
                      )}
                      {detail.catalog?.supported_parameters.includes("max_tokens") &&
                        detail.catalog.max_completion_tokens != null &&
                        validOutputTokens(outputTokensDraft) &&
                        Number(outputTokensDraft) > detail.catalog.max_completion_tokens && (
                          <p className="mm-inline-error" role="status">
                            目前高於目錄宣告的 {detail.catalog.max_completion_tokens.toLocaleString()} tokens；試跑與依模型設定的新測試會被拒絕，請調低。
                          </p>
                        )}
                      {effortError && <p className="mm-inline-error" role="alert">{effortError}</p>}
                      {effortNotice && <p className="mm-inline-success" role="status">{effortNotice}</p>}
                    </div>
                  )}
                  {detail.catalog && (
                    <>
                      <dl className="mm-detail-list">
                        <dt>Context</dt>
                        <dd>{detail.catalog.context_length?.toLocaleString() || "未知"}</dd>
                        <dt>目錄參考價</dt>
                        <dd>{detail.catalog.fixed_model
                          ? `輸入 ${catalogPrice(detail.catalog.pricing.prompt)} ／ 輸出 ${catalogPrice(detail.catalog.pricing.completion)}（每百萬 tokens）`
                          : "動態路由，依實際模型計費"}</dd>
                        <dt>能力</dt>
                        <dd>{detail.catalog.supported_parameters.join("、") || "未提供"}</dd>
                      </dl>
                      <p className="mm-form-help">{detail.catalog.fixed_model
                        ? "目錄價格僅供參考，實際費用以服務回報為準。"
                        : "每題可能使用不同模型；測試結果會記錄實際模型與上游回報的費用。"}</p>
                      {!detail.catalog.supported_parameters.includes("temperature") && (
                        <p className="mm-form-help">此模型未宣告支援 Temperature；正式測試會略過該設定。</p>
                      )}
                    </>
                  )}
                </div>
                <div className="mm-drawer-actions">
                  {connection &&
                    status.tone !== "ready" &&
                    detail.enabled !== false && (
                      <button
                        className="secondary"
                        onClick={() => {
                          setDetailId("");
                          onConnection(connection.id);
                        }}
                      >
                        前往廠商連線
                      </button>
                    )}
                  {connection &&
                    detail.enabled !== false &&
                    connection.enabled &&
                    status.label === "目前不可用" && (
                      <button
                        className="secondary"
                        onClick={() => {
                          setDetailId("");
                          onAdd(connection.id);
                        }}
                      >
                        選擇替代模型
                      </button>
                    )}
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => onToggle(detail)}
                  >
                    {detail.enabled === false ? "啟用模型" : "停用模型"}
                  </button>
                  <button
                    className="secondary mm-danger"
                    disabled={busy}
                    onClick={() => {
                      setDetailId("");
                      onDelete(detail);
                    }}
                  >
                    <Trash2 size={14} />
                    刪除模型
                  </button>
                  <button
                    className="primary"
                    disabled={busy || status.tone !== "ready"}
                    onClick={() => {
                      setDetailId("");
                      onTrial(detail);
                    }}
                  >
                    試跑模型
                  </button>
                </div>
              </aside>
            </div>
          );
        })()}
    </section>
  );
}
