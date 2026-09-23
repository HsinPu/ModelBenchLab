import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  KeyRound,
  Layers3,
  Link2,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, Model, Connection, CatalogPage } from "../../api";
import "./models.css";

const statuses: Record<string, string> = {
  unverified: "待驗證",
  verified: "已驗證",
  invalid: "金鑰無效",
  error: "驗證失敗",
};
const stamp = (value: string | null) =>
  value ? new Date(value).toLocaleString("zh-TW") : "尚未同步";
const price = (value: string | null | undefined) =>
  value == null
    ? "未知"
    : "$" +
      (Number(value) * 1_000_000).toLocaleString("en-US", {
        maximumFractionDigits: 4,
      });
const credits = (value: number | null | undefined) =>
  value == null
    ? "未提供"
    : "$" + value.toLocaleString("en-US", { maximumFractionDigits: 4 });

export default function ModelManagement({
  models,
  onRefresh,
  onAddManual,
}: {
  models: Model[];
  onRefresh: () => Promise<void>;
  onAddManual: () => void;
}) {
  const [tab, setTab] = useState("models");
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState("");
  const [form, setForm] = useState<{
    id: string;
    name: string;
    api_key: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [catalog, setCatalog] = useState<CatalogPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [q, setQ] = useState("");
  const [author, setAuthor] = useState("");
  const [freeOnly, setFreeOnly] = useState(false);
  const [textOnly, setTextOnly] = useState(true);
  const [capability, setCapability] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [trial, setTrial] = useState<Model | null>(null);
  const connection = connections.find((c) => c.id === connectionId);
  const routed = connections.filter((c) => c.provider === "openrouter");

  async function reload() {
    const rows = await api<Connection[]>("/connections");
    setConnections(rows);
    setConnectionId(
      (current) =>
        current || rows.find((c) => c.provider === "openrouter")?.id || "",
    );
    await onRefresh();
  }
  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, []);
  async function action(fn: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失敗");
    } finally {
      try {
        await reload();
      } catch {
        setError((e) => e || "無法更新資料，請重新整理頁面");
      }
      lock.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    if (tab !== "catalog" || !connectionId) return;
    let stale = false;
    setLoading(true);
    setCatalog(null);
    const timer = setTimeout(() => {
      const query = new URLSearchParams({
        q,
        author,
        free_only: String(freeOnly),
        text_only: String(textOnly),
        capability,
        offset: String(offset),
      });
      api<CatalogPage>(`/connections/${connectionId}/catalog?${query}`)
        .then((data) => {
          if (!stale) setCatalog(data);
        })
        .catch((e) => {
          if (!stale) setError(e.message);
        })
        .finally(() => {
          if (!stale) setLoading(false);
        });
    }, 200);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [
    tab,
    connectionId,
    q,
    author,
    freeOnly,
    textOnly,
    capability,
    offset,
    revision,
  ]);

  function chooseConnection(id: string) {
    setConnectionId(id);
    setSelected([]);
    setOffset(0);
    setAuthor("");
    setCatalog(null);
  }
  async function sync(id: string, force = false) {
    await api(`/connections/${id}/sync?force=${force}`, {});
    setRevision((r) => r + 1);
  }
  const ready = Boolean(
    connection?.enabled && connection.status === "verified",
  );

  return (
    <div className="model-management">
      <div className="model-tabs" role="tablist" aria-label="模型管理分類">
        {[
          ["models", "我的模型", models.length],
          ["connections", "廠商連線", connections.length],
          ["catalog", "模型目錄", null],
        ].map(([id, label, count]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => {
              setTab(String(id));
              setError("");
            }}
          >
            {label}
            {count !== null && <span>{count}</span>}
          </button>
        ))}
      </div>
      {error && (
        <div className="management-message error" role="alert">
          {error}
          <button aria-label="關閉錯誤訊息" onClick={() => setError("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {notice && (
        <div className="management-message success" role="status">
          <Check size={17} />
          {notice}
        </div>
      )}

      {tab === "models" && (
        <>
          <div className="provider-intro">
            <span className="tile-icon">
              <Link2 size={24} />
            </span>
            <div>
              <h2>一組連線，加入多個模型</h2>
              <p>
                連接 OpenRouter，從模型目錄挑選要比較的模型。也支援自行設定 API
                端點。
              </p>
            </div>
            <button
              className="primary"
              onClick={() => {
                setTab("connections");
                if (!routed.length)
                  setForm({ id: "", name: "OpenRouter", api_key: "" });
              }}
            >
              <Plus size={16} />
              連接廠商
            </button>
            <button className="secondary" onClick={onAddManual}>
              手動新增
            </button>
          </div>
          <div className="card-grid">
            {models.map((m) => (
              <article className="model-card" key={m.id}>
                <div className="card-top">
                  <span className="tile-icon">
                    <Layers3 size={22} />
                  </span>
                  <span
                    className={
                      "pill " +
                      (m.available === false ? "unavailable" : "neutral")
                    }
                  >
                    {m.provider === "demo"
                      ? "DEMO"
                      : m.provider === "openrouter"
                        ? "OPENROUTER"
                        : "自訂 API"}
                  </span>
                </div>
                <h3>{m.name}</h3>
                <code>{m.model}</code>
                <p>
                  {m.provider === "demo"
                    ? "內建固定回答與模擬延遲，不產生 API 費用。"
                    : m.connection_name || m.endpoint}
                </p>
                {m.available === false && (
                  <p className="unavailable-text">{m.unavailable_reason}</p>
                )}
                {m.catalog && (
                  <div className="model-specs">
                    <span>
                      Context{" "}
                      {m.catalog.context_length?.toLocaleString() || "未知"}
                    </span>
                    <span>
                      輸入 {price(m.catalog.pricing.prompt)} / M tokens
                    </span>
                    <span>
                      輸出 {price(m.catalog.pricing.completion)} / M tokens
                    </span>
                  </div>
                )}
                <div className="card-footer">
                  <small>
                    {m.has_key
                      ? "金鑰已加密"
                      : m.provider === "demo"
                        ? "本機示範"
                        : "無金鑰"}
                  </small>
                  <div className="inline-actions">
                    <button
                      disabled={busy}
                      className="text-button"
                      onClick={() =>
                        action(async () => {
                          await api(
                            `/models/${m.id}`,
                            { enabled: m.enabled === false },
                            "PATCH",
                          );
                        })
                      }
                    >
                      {m.enabled === false ? "啟用" : "停用"}
                    </button>
                    <button
                      disabled={busy || m.available === false}
                      className="text-button"
                      onClick={() => setTrial(m)}
                    >
                      試跑模型 <ArrowRight size={14} />
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
          {!models.length && (
            <div className="empty">尚未加入模型，先連接廠商或手動新增。</div>
          )}
        </>
      )}

      {tab === "connections" && (
        <>
          <div className="management-heading">
            <div>
              <h2>廠商連線</h2>
              <p>金鑰由後端加密保存，同一連線下的模型共用金鑰。</p>
            </div>
            <button
              disabled={busy}
              className="primary"
              onClick={() =>
                setForm({ id: "", name: "OpenRouter", api_key: "" })
              }
            >
              <Plus size={16} />
              新增 OpenRouter 連線
            </button>
          </div>
          {form && (
            <section className="panel connection-form">
              <div className="section-head">
                <h2>{form.id ? "編輯連線 / 更換金鑰" : "連接 OpenRouter"}</h2>
                <button
                  className="icon-button"
                  disabled={busy}
                  aria-label="關閉連線表單"
                  onClick={() => setForm(null)}
                >
                  <X size={18} />
                </button>
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const input = { ...form };
                  action(async () => {
                    const body = {
                      name: input.name,
                      ...(input.api_key ? { api_key: input.api_key } : {}),
                    };
                    const saved = await api<Connection>(
                      input.id ? `/connections/${input.id}` : "/connections",
                      body,
                      input.id ? "PATCH" : "POST",
                    );
                    setForm(null);
                    chooseConnection(saved.id);
                    setNotice(
                      saved.provider === "openrouter"
                        ? "連線已保存。OpenRouter 金鑰須先驗證，再同步模型目錄。"
                        : "手動連線已更新，所屬模型將使用新的設定。",
                    );
                  });
                }}
              >
                <div className="form-grid">
                  <label>
                    連線名稱
                    <input
                      required
                      maxLength={100}
                      value={form.name}
                      onChange={(e) =>
                        setForm({ ...form, name: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    {form.id ? "新 API Key（留白保留原金鑰）" : "API Key"}
                    <input
                      type="password"
                      autoComplete="new-password"
                      required={!form.id}
                      maxLength={4000}
                      placeholder="輸入 API Key"
                      value={form.api_key}
                      onChange={(e) =>
                        setForm({ ...form, api_key: e.target.value })
                      }
                    />
                  </label>
                </div>
                <p className="muted">
                  {form.id
                    ? "更換金鑰後，OpenRouter 連線須重新驗證。已完成的測試結果會保留。"
                    : "API 位址：https://openrouter.ai/api/v1。保存不會發出模型請求。"}
                </p>
                <button className="primary" disabled={busy}>
                  <KeyRound size={15} />
                  {busy ? "保存中…" : "保存連線"}
                </button>
              </form>
            </section>
          )}
          {!connections.length && !form && (
            <div className="empty">
              <Link2 size={30} />
              <h3>尚未連接廠商</h3>
              <p>新增 OpenRouter 連線 → 驗證金鑰 → 同步並挑選模型。</p>
            </div>
          )}
          <div className="connection-list">
            {connections.map((c) => (
              <article className="panel connection-card" key={c.id}>
                <div className="connection-top">
                  <span className="tile-icon">
                    <Link2 size={22} />
                  </span>
                  <div>
                    <h3>{c.name}</h3>
                    <code>
                      {c.provider === "openrouter" ? "OpenRouter" : c.endpoint}
                    </code>
                  </div>
                  <span
                    className={
                      "pill " +
                      (c.enabled && c.status === "verified"
                        ? "verified"
                        : "neutral")
                    }
                  >
                    {!c.enabled
                      ? "已停用"
                      : c.provider !== "openrouter"
                        ? "手動設定"
                        : statuses[c.status] || c.status}
                  </span>
                </div>
                {c.provider === "openrouter" && (
                  <>
                    <div className="connection-facts">
                      <div>
                        <small>金鑰額度上限</small>
                        <strong>
                          {c.usage.limit === null
                            ? "未設限"
                            : credits(c.usage.limit)}
                        </strong>
                      </div>
                      <div>
                        <small>金鑰剩餘額度</small>
                        <strong>{credits(c.usage.limit_remaining)}</strong>
                      </div>
                      <div>
                        <small>金鑰累計用量</small>
                        <strong>{credits(c.usage.usage)}</strong>
                      </div>
                    </div>
                    <p className="muted">
                      以上是金鑰資訊，並非帳戶餘額。最後驗證：
                      {c.last_checked_at
                        ? stamp(c.last_checked_at)
                        : "尚未驗證"}
                    </p>
                  </>
                )}
                {c.error && <p className="unavailable-text">{c.error}</p>}
                <div className="connection-actions">
                  <span className="muted">
                    <ShieldCheck size={14} />
                    {c.has_key ? "金鑰已加密保存" : "未設定金鑰"}
                  </span>
                  <button
                    disabled={busy}
                    className="secondary"
                    onClick={() =>
                      setForm({ id: c.id, name: c.name, api_key: "" })
                    }
                  >
                    編輯 / 更換金鑰
                  </button>
                  <button
                    disabled={busy}
                    className="secondary"
                    onClick={() =>
                      action(async () => {
                        await api(
                          `/connections/${c.id}`,
                          { enabled: !c.enabled },
                          "PATCH",
                        );
                      })
                    }
                  >
                    {c.enabled ? "停用" : "啟用"}
                  </button>
                  {c.provider === "openrouter" && (
                    <>
                      <button
                        className="secondary"
                        disabled={busy || !c.enabled}
                        onClick={() =>
                          action(async () => {
                            await api(`/connections/${c.id}/verify`, {});
                            setNotice("金鑰驗證成功，未發出模型生成請求。");
                          })
                        }
                      >
                        {busy ? "處理中…" : "驗證金鑰"}
                      </button>
                      <button
                        className="primary"
                        disabled={busy || !c.enabled || c.status !== "verified"}
                        onClick={() =>
                          action(async () => {
                            chooseConnection(c.id);
                            await sync(c.id);
                            setTab("catalog");
                          })
                        }
                      >
                        瀏覽模型 <ArrowRight size={15} />
                      </button>
                    </>
                  )}
                </div>
              </article>
            ))}
          </div>
          <div className="hint">
            <ShieldCheck size={18} />
            驗證金鑰僅讀取廠商資訊，不會生成回答。停用連線後，所屬模型將停止發出新請求；進行中的請求仍可能完成。
          </div>
        </>
      )}

      {tab === "catalog" && (
        <>
          <div className="management-heading">
            <div>
              <h2>OpenRouter 模型目錄</h2>
              <p>選擇明確的模型 ID，批次加入比較清單。</p>
            </div>
            <button className="secondary" onClick={() => setTab("connections")}>
              管理連線
            </button>
          </div>
          {!routed.length ? (
            <div className="empty">
              <Search size={30} />
              <h3>連接 OpenRouter 後探索模型</h3>
              <p>驗證金鑰後即可同步名稱、價格、Context 與支援能力。</p>
              <button
                className="primary"
                onClick={() => {
                  setTab("connections");
                  setForm({ id: "", name: "OpenRouter", api_key: "" });
                }}
              >
                新增連線
              </button>
            </div>
          ) : (
            <>
              <section className="panel catalog-controls">
                <div className="catalog-top">
                  <label>
                    使用連線
                    <select
                      value={connectionId}
                      onChange={(e) => chooseConnection(e.target.value)}
                    >
                      {routed.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                          {!c.enabled
                            ? " · 已停用"
                            : c.status !== "verified"
                              ? " · 待驗證"
                              : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div>
                    <small className="muted">最後同步</small>
                    <p>
                      {stamp(
                        catalog?.synced_at ||
                          connection?.last_synced_at ||
                          null,
                      )}
                    </p>
                  </div>
                  <button
                    className="secondary"
                    disabled={busy || !ready}
                    onClick={() =>
                      action(async () => {
                        await sync(connectionId, true);
                        setNotice("模型目錄已更新。");
                      })
                    }
                  >
                    <RefreshCw size={15} className={busy ? "spin" : ""} />
                    {busy ? "同步中…" : "更新目錄"}
                  </button>
                </div>
                <div className="catalog-filters">
                  <label>
                    搜尋模型
                    <input
                      type="search"
                      value={q}
                      placeholder="模型名稱或 ID"
                      onChange={(e) => {
                        setQ(e.target.value);
                        setOffset(0);
                      }}
                    />
                  </label>
                  <label>
                    模型作者
                    <select
                      value={author}
                      onChange={(e) => {
                        setAuthor(e.target.value);
                        setOffset(0);
                      }}
                    >
                      <option value="">全部作者</option>
                      {(catalog?.authors || (author ? [author] : [])).map(
                        (a) => (
                          <option key={a}>{a}</option>
                        ),
                      )}
                    </select>
                  </label>
                  <label>
                    支援能力
                    <select
                      value={capability}
                      onChange={(e) => {
                        setCapability(e.target.value);
                        setOffset(0);
                      }}
                    >
                      <option value="">不限</option>
                      <option value="tools">工具呼叫</option>
                      <option value="structured_outputs">結構化輸出</option>
                      <option value="reasoning">推理</option>
                      <option value="temperature">Temperature</option>
                    </select>
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={freeOnly}
                      onChange={(e) => {
                        setFreeOnly(e.target.checked);
                        setOffset(0);
                      }}
                    />
                    僅免費
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={textOnly}
                      onChange={(e) => {
                        setTextOnly(e.target.checked);
                        setOffset(0);
                      }}
                    />
                    文字輸入 / 輸出
                  </label>
                </div>
              </section>
              {!ready && (
                <div className="hint">
                  此連線須啟用並通過驗證後，才能更新目錄或加入模型。目前仍可檢視本機快取。
                </div>
              )}
              {catalog?.error && (
                <div className="management-message error">
                  上次同步失敗：{catalog.error}。以下為上次成功同步的資料。
                </div>
              )}
              <section className="panel catalog-panel">
                <div className="catalog-selection">
                  <span>
                    {loading ? "載入中…" : `${catalog?.total || 0} 個模型`} ·
                    已選 {selected.length} / 100
                  </span>
                  <div className="inline-actions">
                    <button
                      className="text-button"
                      disabled={!selected.length || busy}
                      onClick={() => setSelected([])}
                    >
                      清除選取
                    </button>
                    <button
                      className="primary"
                      disabled={busy || loading || !ready || !selected.length}
                      onClick={() =>
                        action(async () => {
                          const result = await api<{
                            created: number;
                            skipped: number;
                          }>(`/connections/${connectionId}/models`, {
                            model_ids: selected,
                          });
                          setSelected([]);
                          setRevision((r) => r + 1);
                          setNotice(
                            `已加入 ${result.created} 個模型，略過 ${result.skipped} 個既有模型。可至「我的模型」查看或建立測試。`,
                          );
                        })
                      }
                    >
                      <Plus size={15} />
                      加入我的模型
                      {selected.length > 0 && `（${selected.length}）`}
                    </button>
                  </div>
                </div>
                {!loading && catalog?.items.length ? (
                  <div className="table-wrap">
                    <table className="catalog-table">
                      <thead>
                        <tr>
                          <th>
                            <input
                              type="checkbox"
                              aria-label="選取此頁可加入的模型"
                              disabled={busy || !ready}
                              checked={
                                catalog.items.some(
                                  (m) => !m.added && m.selectable,
                                ) &&
                                catalog.items
                                  .filter((m) => !m.added && m.selectable)
                                  .every((m) => selected.includes(m.model_id))
                              }
                              onChange={(e) => {
                                const ids = catalog.items
                                  .filter((m) => !m.added && m.selectable)
                                  .map((m) => m.model_id);
                                setSelected(
                                  e.target.checked
                                    ? [...new Set([...selected, ...ids])].slice(
                                        0,
                                        100,
                                      )
                                    : selected.filter(
                                        (id) => !ids.includes(id),
                                      ),
                                );
                              }}
                            />
                          </th>
                          <th>模型</th>
                          <th>Context</th>
                          <th>
                            輸入 / 輸出價格<small>USD / 百萬 tokens</small>
                          </th>
                          <th>能力 / 狀態</th>
                        </tr>
                      </thead>
                      <tbody>
                        {catalog.items.map((m) => (
                          <tr key={m.id}>
                            <td>
                              <input
                                type="checkbox"
                                aria-label={`選取 ${m.name}`}
                                disabled={
                                  busy ||
                                  !ready ||
                                  m.added ||
                                  !m.selectable ||
                                  (selected.length >= 100 &&
                                    !selected.includes(m.model_id))
                                }
                                checked={selected.includes(m.model_id)}
                                onChange={(e) =>
                                  setSelected(
                                    e.target.checked
                                      ? [...selected, m.model_id]
                                      : selected.filter(
                                          (id) => id !== m.model_id,
                                        ),
                                  )
                                }
                              />
                            </td>
                            <td>
                              <strong>{m.name}</strong>
                              <code>{m.model_id}</code>
                              <small>
                                {m.details.input_modalities.join(" + ")} →{" "}
                                {m.details.output_modalities.join(" + ")}
                              </small>
                            </td>
                            <td>
                              {m.details.context_length?.toLocaleString() ||
                                "未知"}
                            </td>
                            <td>
                              {price(m.details.pricing.prompt)} /{" "}
                              {price(m.details.pricing.completion)}
                              {m.free && (
                                <small className="free-label">
                                  目錄標示免費
                                </small>
                              )}
                            </td>
                            <td>
                              <div className="capability-tags">
                                {m.added ? (
                                  <span className="pill verified">已加入</span>
                                ) : !m.selectable ? (
                                  <span className="pill neutral">
                                    此版不支援
                                  </span>
                                ) : (
                                  m.details.supported_parameters
                                    .filter((p) =>
                                      [
                                        "tools",
                                        "reasoning",
                                        "structured_outputs",
                                      ].includes(p),
                                    )
                                    .map((p) => (
                                      <span className="pill neutral" key={p}>
                                        {p === "tools"
                                          ? "工具"
                                          : p === "reasoning"
                                            ? "推理"
                                            : "JSON"}
                                      </span>
                                    ))
                                )}
                              </div>
                              {m.selectable &&
                                !["temperature", "max_tokens"].every((p) =>
                                  m.details.supported_parameters.includes(p),
                                ) && (
                                  <small className="unavailable-text">
                                    不支援目前測試參數
                                  </small>
                                )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="empty">
                    {loading
                      ? "正在讀取模型目錄…"
                      : !catalog?.synced_at
                        ? "點選「更新目錄」取得模型清單。"
                        : "沒有符合條件的模型，請調整篩選。"}
                  </div>
                )}
                <div className="catalog-pagination">
                  <small>
                    {catalog?.total
                      ? `${offset + 1}–${Math.min(offset + 50, catalog.total)} / ${catalog.total}`
                      : "0 個模型"}
                  </small>
                  <div className="inline-actions">
                    <button
                      className="secondary"
                      disabled={loading || offset === 0}
                      onClick={() => setOffset((o) => Math.max(0, o - 50))}
                    >
                      上一頁
                    </button>
                    <button
                      className="secondary"
                      disabled={loading || offset + 50 >= (catalog?.total || 0)}
                      onClick={() => setOffset((o) => o + 50)}
                    >
                      下一頁
                    </button>
                  </div>
                </div>
              </section>
              <div className="hint">
                目錄快取 15
                分鐘；「更新目錄」可立即重新同步。價格僅供參考，免費模型仍受廠商限流。此版僅執行文字評估，工具與推理標籤用於查看能力。
              </div>
            </>
          )}
        </>
      )}

      {trial && (
        <div className="modal-backdrop">
          <section
            className="modal trial-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="trial-title"
          >
            <div className="modal-head">
              <h2 id="trial-title">試跑 {trial.name}</h2>
              <button
                className="icon-button"
                disabled={busy}
                aria-label="關閉試跑"
                onClick={() => setTrial(null)}
              >
                <X size={20} />
              </button>
            </div>
            {error && (
              <div className="management-message error" role="alert">
                {error}
              </div>
            )}
            <p>
              {trial.provider === "demo"
                ? "此模型提供固定示範回答，不產生費用。"
                : "將發送一筆「Reply OK」短請求，輸出上限為 8 tokens，可能產生 API 費用。這次試跑不加入正式測試紀錄。"}
            </p>
            <div className="inline-actions">
              <button
                disabled={busy}
                className="secondary"
                onClick={() => setTrial(null)}
              >
                取消
              </button>
              <button
                disabled={busy}
                className="primary"
                onClick={() =>
                  action(async () => {
                    const r = await api<{
                      latency_ms: number;
                      cost: string | null;
                      upstream_provider: string | null;
                    }>(`/models/${trial.id}/test`, {});
                    setTrial(null);
                    setNotice(
                      `試跑成功 · ${r.latency_ms} ms${trial.provider === "demo" ? " · 示範" : ` · 費用 ${r.cost == null ? "未知" : "$" + r.cost}${r.upstream_provider ? " · " + r.upstream_provider : ""}`}`,
                    );
                  })
                }
              >
                {busy ? "試跑中…" : "開始試跑"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
