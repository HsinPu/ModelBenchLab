import { useState, type FormEvent } from "react";
import { api, type Connection, type ProviderType } from "../../api";
import { providerFor } from "./modelUi";

export default function ConnectionForm({
  initial,
  types,
  onSaved,
  onCancel,
}: {
  initial?: Connection | null;
  types: ProviderType[];
  onSaved: (connection: Connection) => Promise<void>;
  onCancel: () => void;
}) {
  const [form, setForm] = useState({
    provider: initial?.provider || "",
    name: initial?.name || "",
    endpoint: initial?.endpoint || "",
    api_key: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const type = providerFor(types, form.provider);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const body = {
        name: form.name,
        ...(!initial ? { provider: form.provider } : {}),
        ...(type?.requires_endpoint ? { endpoint: form.endpoint } : {}),
        ...(form.api_key ? { api_key: form.api_key } : {}),
      };
      const saved = await api<Connection>(
        initial ? `/connections/${initial.id}` : "/connections",
        body,
        initial ? "PATCH" : "POST",
      );
      await onSaved(saved);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "無法保存連線");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="mm-connection-form" onSubmit={save}>
      {error && (
        <p className="mm-inline-error" role="alert">
          {error}
        </p>
      )}
      <div className="form-grid">
        <label>
          服務類型
          {initial ? (
            <input value={type?.label || initial.provider} disabled />
          ) : (
            <select
              required
              value={form.provider}
              onChange={(event) => {
                const chosen = providerFor(types, event.target.value);
                setForm({
                  provider: event.target.value,
                  name: chosen?.requires_endpoint ? "" : chosen?.label || "",
                  endpoint: "",
                  api_key: "",
                });
              }}
            >
              <option value="">選擇服務類型</option>
              {types.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          )}
        </label>
        <label>
          連線名稱
          <input
            required
            maxLength={100}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            placeholder="方便辨識這組連線的名稱"
          />
        </label>
        {type?.requires_endpoint && (
          <label className="mm-full-field">
            API Base URL
            <input
              required
              type="url"
              maxLength={2000}
              placeholder="例如 http://localhost:11434/v1"
              value={form.endpoint}
              onChange={(event) =>
                setForm({ ...form, endpoint: event.target.value })
              }
            />
          </label>
        )}
        <label className="mm-full-field">
          {initial ? "新 API Key（留白保留原金鑰）" : "API Key"}
          <input
            type="password"
            autoComplete="new-password"
            required={!initial && type?.requires_api_key}
            maxLength={4000}
            value={form.api_key}
            onChange={(event) =>
              setForm({ ...form, api_key: event.target.value })
            }
            placeholder={
              type?.requires_api_key ? "此服務需要 API Key" : "沒有金鑰可留空"
            }
          />
        </label>
      </div>
      <p className="mm-form-help">
        {type?.description || "先選擇服務類型；保存連線時不會發出模型請求。"}
        {initial && type?.verification === "metadata" && form.api_key
          ? " 更換金鑰後須重新驗證。"
          : ""}
      </p>
      <div className="mm-form-actions">
        <button
          type="button"
          className="secondary"
          onClick={onCancel}
          disabled={busy}
        >
          取消
        </button>
        <button className="primary" disabled={busy}>
          {busy ? "保存中…" : "保存連線"}
        </button>
      </div>
    </form>
  );
}
