import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, Plus, RefreshCw, Search, X } from "lucide-react";
import {
  api,
  type CatalogPage,
  type Connection,
  type Model,
  type ProviderType,
  type ReasoningEffort,
} from "../../api";
import ConnectionForm from "./ConnectionForm";
import ReasoningEffortField from "./ReasoningEffortField";
import OutputTokensField, { DEFAULT_OUTPUT_TOKENS, validOutputTokens } from "./OutputTokensField";
import {
  catalogPrice,
  connectionReady,
  connectionStatus,
  providerFor,
  stamp,
} from "./modelUi";
import { useDialogFocus } from "./useDialogFocus";

export default function AddModelFlow({
  initialConnectionId,
  connections,
  models,
  types,
  onRefresh,
  onCreated,
  onManageConnection,
  onClose,
}: {
  initialConnectionId: string;
  connections: Connection[];
  models: Model[];
  types: ProviderType[];
  onRefresh: () => Promise<void>;
  onCreated: (ids: string[], message: string) => Promise<void>;
  onManageConnection: (id: string) => void;
  onClose: () => void;
}) {
  const [connectionId, setConnectionId] = useState(initialConnectionId);
  const [freshConnection, setFreshConnection] = useState<Connection | null>(
    null,
  );
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [modelId, setModelId] = useState("");
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort | "">("");
  const [outputTokens, setOutputTokens] = useState(String(DEFAULT_OUTPUT_TOKENS));
  const [syncedId, setSyncedId] = useState("");
  const [catalog, setCatalog] = useState<CatalogPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [query, setQuery] = useState("");
  const [author, setAuthor] = useState("");
  const [freeOnly, setFreeOnly] = useState(false);
  const [capability, setCapability] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const dialogRef = useDialogFocus<HTMLElement>(true, () => {
    if (!busy) onClose();
  });
  const connection =
    connections.find((item) => item.id === connectionId) ||
    (freshConnection?.id === connectionId ? freshConnection : null);
  const type = connection ? providerFor(types, connection.provider) : undefined;
  const ready = Boolean(connection && connectionReady(connection, type));
  const selectedIds = Object.keys(selected);
  useEffect(() => {
    dialogRef.current?.querySelector<HTMLElement>("#mm-flow-title")?.focus();
  }, [connectionId, creating]);

  function chooseConnection(id: string) {
    setConnectionId(id);
    setCreating(false);
    setError("");
    setSyncedId("");
    setCatalog(null);
    setSelected({});
    setOffset(0);
    setQuery("");
    setAuthor("");
    setName("");
    setModelId("");
    setReasoningEffort("");
  }

  useEffect(() => {
    if (
      !connection ||
      !type?.supports_catalog ||
      !ready ||
      syncedId === connection.id
    )
      return;
    let stale = false;
    setLoading(true);
    setError("");
    api(`/connections/${connection.id}/sync`, {})
      .then(async () => {
        if (!stale) {
          setSyncedId(connection.id);
          await onRefresh();
        }
      })
      .catch((cause) => {
        if (!stale)
          setError(cause instanceof Error ? cause.message : "無法同步模型目錄");
      })
      .finally(() => {
        if (!stale) setLoading(false);
      });
    return () => {
      stale = true;
    };
  }, [
    connection?.id,
    connection?.enabled,
    connection?.status,
    type?.supports_catalog,
    ready,
    syncedId,
  ]);

  useEffect(() => {
    if (!connection || !type?.supports_catalog || syncedId !== connection.id)
      return;
    let stale = false;
    setLoading(true);
    const timer = setTimeout(() => {
      const params = new URLSearchParams({
        q: query,
        author,
        free_only: String(freeOnly),
        text_only: "true",
        capability,
        unadded_only: String(!showAll),
        selectable_only: String(!showAll),
        offset: String(offset),
        limit: "30",
      });
      api<CatalogPage>(`/connections/${connection.id}/catalog?${params}`)
        .then((page) => {
          if (!stale) {
            setCatalog(page);
            setError("");
          }
        })
        .catch((cause) => {
          if (!stale)
            setError(
              cause instanceof Error ? cause.message : "無法讀取模型目錄",
            );
        })
        .finally(() => {
          if (!stale) setLoading(false);
        });
    }, 180);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [
    connection?.id,
    type?.supports_catalog,
    syncedId,
    query,
    author,
    freeOnly,
    capability,
    showAll,
    offset,
    revision,
  ]);

  async function verify() {
    if (!connection || busy) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<Connection>(
        `/connections/${connection.id}/verify`,
        {},
      );
      setFreshConnection(updated);
      await onRefresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "金鑰驗證失敗");
    } finally {
      setBusy(false);
    }
  }

  async function refreshCatalog() {
    if (!connection || busy) return;
    setBusy(true);
    setError("");
    try {
      await api(`/connections/${connection.id}/sync?force=true`, {});
      await onRefresh();
      setSyncedId(connection.id);
      setRevision((value) => value + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "無法更新模型目錄");
    } finally {
      setBusy(false);
    }
  }

  async function saveManual(event: FormEvent) {
    event.preventDefault();
    if (!connection || busy || !validOutputTokens(outputTokens)) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ created: boolean; id: string }>(
        `/connections/${connection.id}/models/manual`,
        { name, model_id: modelId, reasoning_effort: reasoningEffort || null, max_output_tokens: Number(outputTokens) },
      );
      if (!result.created) {
        setError("這個模型 ID 已在此連線中；請回到「我的模型」查看。");
        return;
      }
      await onCreated(
        [result.id],
        "模型已加入。需要確認連通性時，可在列表中試跑。",
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "無法加入模型");
    } finally {
      setBusy(false);
    }
  }

  async function saveCatalog() {
    if (!connection || !selectedIds.length || busy || !validOutputTokens(outputTokens)) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{
        created: number;
        skipped: number;
        ids: string[];
      }>(`/connections/${connection.id}/models`, {
        model_ids: selectedIds,
        reasoning_effort: reasoningEffort || null,
        max_output_tokens: Number(outputTokens),
      });
      await onCreated(
        result.ids,
        result.created
          ? `已加入 ${result.created} 個模型${result.skipped ? `，略過 ${result.skipped} 個已存在模型` : ""}。可在列表中試跑。`
          : "所選模型已在這組連線中。",
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "無法加入模型");
    } finally {
      setBusy(false);
    }
  }

  function toggleSelection(model: { model_id: string; name: string }) {
    setSelected((current) => {
      const next = { ...current };
      if (next[model.model_id]) delete next[model.model_id];
      else if (Object.keys(next).length < 100)
        next[model.model_id] = model.name;
      return next;
    });
  }

  return (
    <div
      className="mm-flow-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="mm-flow"
        role="dialog"
        aria-modal="true"
        aria-labelledby="mm-flow-title"
      >
        <div className="mm-flow-head">
          <div>
            <small>模型管理 / 加入模型</small>
            <h2 id="mm-flow-title" tabIndex={-1}>
              {creating
                ? "建立新連線"
                : connection
                  ? `從 ${connection.name} 加入模型`
                  : "選擇模型來源"}
            </h2>
          </div>
          <button
            className="mm-icon-button"
            aria-label="關閉加入模型"
            disabled={busy}
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        <div className="mm-flow-steps">
          <span className={!connection || creating ? "active" : "done"}>
            1 選擇連線
          </span>
          <span className={connection && !creating ? "active" : ""}>
            2 選擇模型
          </span>
        </div>
        <div className="mm-flow-body">
          {error && (
            <div className="mm-inline-error" role="alert">
              {error}
            </div>
          )}
          {creating ? (
            <>
              <button
                className="mm-back-button"
                onClick={() => setCreating(false)}
              >
                <ArrowLeft size={15} />
                返回連線清單
              </button>
              <ConnectionForm
                types={types}
                onCancel={() => setCreating(false)}
                onSaved={async (saved) => {
                  setFreshConnection(saved);
                  chooseConnection(saved.id);
                  await onRefresh();
                }}
              />
            </>
          ) : !connection ? (
            <>
              <p className="mm-flow-intro">
                選一組現有連線，或建立新連線。模型會共用該連線的位址與金鑰。
              </p>
              <div className="mm-source-list">
                {connections.map((item) => {
                  const provider = providerFor(types, item.provider);
                  return (
                    <button
                      key={item.id}
                      className="mm-source"
                      onClick={() => chooseConnection(item.id)}
                    >
                      <span>
                        <strong>{item.name}</strong>
                        <small>
                          {provider?.label || item.provider} ·{" "}
                          {
                            models.filter(
                              (model: Model) => model.connection_id === item.id,
                            ).length
                          }{" "}
                          個模型
                        </small>
                      </span>
                      <span
                        className={`mm-status ${connectionReady(item, provider) ? "ready" : "warning"}`}
                      >
                        {connectionStatus(item, provider)}
                      </span>
                    </button>
                  );
                })}
              </div>
              <button
                className="mm-new-source"
                onClick={() => {
                  setCreating(true);
                  setError("");
                }}
              >
                <Plus size={17} />
                建立新連線
              </button>
            </>
          ) : (
            <>
              <div className="mm-flow-context">
                <button
                  className="mm-back-button"
                  onClick={() => chooseConnection("")}
                >
                  <ArrowLeft size={15} />
                  更換連線
                </button>
                <span className={`mm-status ${ready ? "ready" : "warning"}`}>
                  {connectionStatus(connection, type)}
                </span>
              </div>
              {!connection.enabled ? (
                <div className="mm-empty">
                  <h3>連線已停用</h3>
                  <p>啟用後才能加入模型。</p>
                  <button
                    className="secondary"
                    onClick={() => onManageConnection(connection.id)}
                  >
                    前往廠商連線
                  </button>
                </div>
              ) : type?.verification === "metadata" &&
                connection.status !== "verified" ? (
                <div className="mm-empty">
                  <h3>先驗證連線金鑰</h3>
                  <p>這項驗證只讀取金鑰資訊，不會發出模型生成請求。</p>
                  <button className="primary" disabled={busy} onClick={verify}>
                    {busy ? "驗證中…" : "驗證金鑰並繼續"}
                  </button>
                  <button
                    className="text-button"
                    onClick={() => onManageConnection(connection.id)}
                  >
                    管理連線
                  </button>
                </div>
              ) : type?.supports_catalog ? (
                <>
                  <div className="mm-catalog-top">
                    <label className="mm-search">
                      <Search size={16} aria-hidden="true" />
                      <span className="sr-only">搜尋目錄模型</span>
                      <input
                        type="search"
                        placeholder="搜尋模型名稱或 ID"
                        value={query}
                        onChange={(event) => {
                          setQuery(event.target.value);
                          setOffset(0);
                        }}
                      />
                    </label>
                    <button
                      className="secondary"
                      disabled={busy || loading}
                      onClick={refreshCatalog}
                    >
                      <RefreshCw size={14} />
                      更新目錄
                    </button>
                  </div>
                  <div className="mm-catalog-subhead">
                    <span>
                      {loading
                        ? "載入目錄中…"
                        : `${catalog?.total || 0} 個模型`}{" "}
                      · 最後同步{" "}
                      {stamp(catalog?.synced_at || connection.last_synced_at)}
                    </span>
                    <button
                      className="text-button"
                      onClick={() => setAdvanced(!advanced)}
                      aria-expanded={advanced}
                    >
                      {advanced ? "收起篩選" : "進階篩選"}
                    </button>
                  </div>
                  {advanced && (
                    <div className="mm-advanced-filters">
                      <label>
                        作者
                        <select
                          value={author}
                          onChange={(event) => {
                            setAuthor(event.target.value);
                            setOffset(0);
                          }}
                        >
                          <option value="">全部作者</option>
                          {(catalog?.authors || []).map((item) => (
                            <option key={item} value={item}>
                              {item}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        能力
                        <select
                          value={capability}
                          onChange={(event) => {
                            setCapability(event.target.value);
                            setOffset(0);
                          }}
                        >
                          <option value="">不限</option>
                          <option value="tools">工具</option>
                          <option value="structured_outputs">JSON</option>
                          <option value="reasoning">推理</option>
                        </select>
                      </label>
                      <label className="mm-checkbox">
                        <input
                          type="checkbox"
                          checked={freeOnly}
                          onChange={(event) => {
                            setFreeOnly(event.target.checked);
                            setOffset(0);
                          }}
                        />
                        僅免費
                      </label>
                      <label className="mm-checkbox">
                        <input
                          type="checkbox"
                          checked={showAll}
                          onChange={(event) => {
                            setShowAll(event.target.checked);
                            setOffset(0);
                          }}
                        />
                        顯示已加入模型
                      </label>
                    </div>
                  )}
                  {loading && !catalog ? (
                    <div className="mm-empty">正在取得模型目錄…</div>
                  ) : !catalog?.items.length ? (
                    <div className="mm-empty">
                      <h3>沒有符合條件的模型</h3>
                      <p>
                        {error
                          ? "可重試更新目錄，已選取模型仍會保留。"
                          : "試試其他關鍵字或展開進階篩選。"}
                      </p>
                    </div>
                  ) : (
                    <div className="mm-catalog-list">
                      {catalog.items.map((item) => {
                        const eligible = item.selectable && !item.added;
                        const omittedParameters = ["temperature", "max_tokens"].filter(
                          (parameter) => !item.details.supported_parameters.includes(parameter),
                        );
                        return (
                          <label
                            key={item.id}
                            className={`mm-catalog-item ${!eligible ? "unavailable" : ""}`}
                          >
                            <input
                              type="checkbox"
                              disabled={
                                !eligible ||
                                (selectedIds.length >= 100 &&
                                  !selected[item.model_id])
                              }
                              checked={Boolean(selected[item.model_id])}
                              onChange={() => toggleSelection(item)}
                              aria-label={`選取 ${item.name}`}
                            />
                            <span className="mm-catalog-name">
                              <strong>{item.name}</strong>
                              <code>{item.model_id}</code>
                              {!item.details.fixed_model && (
                                <small className="mm-catalog-note">動態路由：每題可能使用不同模型，結果會記錄實際模型。</small>
                              )}
                              {omittedParameters.length > 0 && (
                                <small className="mm-catalog-note">請求會略過不支援的參數：{omittedParameters.join("、")}</small>
                              )}
                            </span>
                            <span className="mm-catalog-meta">
                              {item.details.context_length?.toLocaleString() ||
                                "未知"}{" "}
                              Context
                            </span>
                            <span className="mm-catalog-meta">
                              {item.details.fixed_model
                                ? `${catalogPrice(item.details.pricing.prompt)} / ${catalogPrice(item.details.pricing.completion)}`
                                : "依實際模型計費"}
                              <small>{item.details.fixed_model ? "輸入 / 輸出 · 百萬 tokens" : "目錄價格不代表最終費用"}</small>
                            </span>
                            <span className="mm-catalog-tag">
                              {item.added
                                ? "已加入"
                                : !item.selectable
                                  ? "無文字回答"
                                  : !item.details.fixed_model
                                    ? "可加入 · 動態路由"
                                    : item.free
                                      ? "免費"
                                      : "可加入"}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                  <div className="mm-pagination">
                    <span>
                      {catalog?.total
                        ? `${offset + 1}–${Math.min(offset + 30, catalog.total)} / ${catalog.total}`
                        : "0 個模型"}
                    </span>
                    <div>
                      <button
                        className="secondary"
                        disabled={loading || offset === 0}
                        onClick={() => setOffset(Math.max(0, offset - 30))}
                      >
                        上一頁
                      </button>
                      <button
                        className="secondary"
                        disabled={
                          loading || offset + 30 >= (catalog?.total || 0)
                        }
                        onClick={() => setOffset(offset + 30)}
                      >
                        下一頁
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <form className="mm-manual-form" onSubmit={saveManual}>
                  <p>
                    填入服務提供的精確模型
                    ID。這組連線可以加入多個模型，加入時不會發出請求。
                  </p>
                  <label>
                    模型 ID
                    <input
                      required
                      maxLength={200}
                      placeholder="例如 llama3.2:latest"
                      value={modelId}
                      onChange={(event) => setModelId(event.target.value)}
                    />
                  </label>
                  <label>
                    顯示名稱
                    <input
                      required
                      maxLength={100}
                      placeholder="例如 Local / Llama 3.2"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                    />
                  </label>
                  <ReasoningEffortField
                    value={reasoningEffort}
                    onChange={setReasoningEffort}
                    disabled={busy}
                  />
                  <OutputTokensField value={outputTokens} onChange={setOutputTokens} disabled={busy} />
                  <p className="mm-form-help">
                    預設 128,000 tokens，可自行調整；上限包含可能使用的推理 token，不代表每次都會用完。若高於模型目錄宣告的上限，請先調低設定。
                  </p>
                  <button className="primary" disabled={busy || !validOutputTokens(outputTokens)}>
                    {busy ? "加入中…" : "加入模型"}
                  </button>
                </form>
              )}
            </>
          )}
        </div>
        {connection && type?.supports_catalog && ready && (
          <div className="mm-selection-bar">
            <div>
              <strong>已選 {selectedIds.length} 個模型</strong>
              {selectedIds.length > 0 && (
                <div className="mm-selected-tags">
                  {selectedIds.map((id) => (
                    <button
                      key={id}
                      className="mm-selected-tag"
                      onClick={() =>
                        setSelected((current) => {
                          const next = { ...current };
                          delete next[id];
                          return next;
                        })
                      }
                    >
                      {selected[id]} <X size={12} />
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="mm-selection-settings">
              <ReasoningEffortField
                value={reasoningEffort}
                onChange={setReasoningEffort}
                disabled={busy}
              />
              <OutputTokensField value={outputTokens} onChange={setOutputTokens} disabled={busy} />
              <small>套用至本次加入的模型。若高於目錄宣告的輸出上限，試跑或建立測試時會提示調低。</small>
            </div>
            <button
              className="primary"
              disabled={busy || !selectedIds.length || !validOutputTokens(outputTokens)}
              onClick={saveCatalog}
            >
              {busy ? "加入中…" : `加入 ${selectedIds.length} 個模型`}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
