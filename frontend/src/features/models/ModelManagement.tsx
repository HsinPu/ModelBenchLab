import { useEffect, useRef, useState } from "react";
import { Check, X } from "lucide-react";
import { api, type Connection, type Model, type ProviderType } from "../../api";
import AddModelFlow from "./AddModelFlow";
import ConnectionForm from "./ConnectionForm";
import ConnectionList from "./ConnectionList";
import ModelList from "./ModelList";
import { useDialogFocus } from "./useDialogFocus";
import "./models.css";

type TrialResponse = {
  ok: boolean;
  output: string;
  latency_ms: number;
  cost: string | null;
  upstream_provider: string | null;
};

type TrialResult =
  | { status: "success"; response: TrialResponse }
  | { status: "error"; message: string };

function validTrialTimeout(value: string) {
  const seconds = Number(value);
  return value.trim() !== "" && Number.isInteger(seconds) && seconds >= 5 && seconds <= 600;
}

export default function ModelManagement({
  models,
  onRefresh,
}: {
  models: Model[];
  onRefresh: () => Promise<void>;
}) {
  const [tab, setTab] = useState<"models" | "connections">("models");
  const [connections, setConnections] = useState<Connection[]>([]);
  const [types, setTypes] = useState<ProviderType[]>([]);
  const [addConnectionId, setAddConnectionId] = useState<string | null>(null);
  const [connectionForm, setConnectionForm] = useState<
    "new" | Connection | null
  >(null);
  const [connectionFocus, setConnectionFocus] = useState("");
  const [trial, setTrial] = useState<Model | null>(null);
  const [trialTimeout, setTrialTimeout] = useState("600");
  const [trialResult, setTrialResult] = useState<TrialResult | null>(null);
  const [deletingModel, setDeletingModel] = useState<Model | null>(null);
  const [highlightId, setHighlightId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const lock = useRef(false);
  const connectionFormRef = useDialogFocus<HTMLElement>(
    Boolean(connectionForm),
    () => setConnectionForm(null),
  );
  const trialRef = useDialogFocus<HTMLElement>(Boolean(trial), () => {
    if (!busy) closeTrial();
  });
  const deleteRef = useDialogFocus<HTMLElement>(Boolean(deletingModel), () => {
    if (!busy) setDeletingModel(null);
  });

  async function reload() {
    const [connectionRows, providerRows] = await Promise.all([
      api<Connection[]>("/connections"),
      api<ProviderType[]>("/providers"),
    ]);
    setConnections(connectionRows);
    setTypes(providerRows);
    await onRefresh();
  }
  useEffect(() => {
    reload().catch((cause) =>
      setError(cause instanceof Error ? cause.message : "無法讀取模型資料"),
    );
  }, []);

  async function action(fn: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "操作失敗");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  function openConnection(id: string) {
    setTab("connections");
    setConnectionFocus(id);
  }

  function openTrial(model: Model) {
    setTrialResult(null);
    setTrialTimeout("600");
    setError("");
    setNotice("");
    setTrial(model);
  }

  function closeTrial() {
    setTrial(null);
    setTrialResult(null);
  }

  async function runTrial() {
    const timeout = Number(trialTimeout);
    if (!trial || lock.current || !validTrialTimeout(trialTimeout)) return;
    lock.current = true;
    setBusy(true);
    setTrialResult(null);
    try {
      const response = await api<TrialResponse>(`/models/${trial.id}/test`, { timeout });
      if (!response.ok) throw new Error("試跑未完成，請稍後重試。");
      setTrialResult({ status: "success", response });
    } catch (cause) {
      setTrialResult({
        status: "error",
        message: cause instanceof Error ? cause.message : "模型請求失敗",
      });
    } finally {
      await reload().catch(() => {});
      lock.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="model-management">
      <div className="model-tabs" role="tablist" aria-label="模型管理分類">
        <button
          role="tab"
          aria-selected={tab === "models"}
          onClick={() => {
            setTab("models");
            setError("");
          }}
        >
          我的模型 <span>{models.length}</span>
        </button>
        <button
          role="tab"
          aria-selected={tab === "connections"}
          onClick={() => {
            setTab("connections");
            setError("");
          }}
        >
          廠商連線 <span>{connections.length}</span>
        </button>
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
          <button aria-label="關閉提示" onClick={() => setNotice("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {tab === "models" ? (
        <ModelList
          models={models}
          connections={connections}
          types={types}
          busy={busy}
          highlightId={highlightId}
          onAdd={(id) => setAddConnectionId(id || "")}
          onTrial={openTrial}
          onDelete={(model) => {
            setError("");
            setDeletingModel(model);
          }}
          onConnection={openConnection}
          onRefresh={reload}
          onToggle={(model) =>
            action(async () => {
              await api(
                `/models/${model.id}`,
                { enabled: model.enabled === false },
                "PATCH",
              );
              setNotice(
                model.enabled === false ? "模型已啟用。" : "模型已停用。",
              );
            })
          }
        />
      ) : (
        <ConnectionList
          connections={connections}
          models={models}
          types={types}
          focusedId={connectionFocus}
          busy={busy}
          onNew={() => setConnectionForm("new")}
          onAddModel={(connection) => setAddConnectionId(connection.id)}
          onEdit={setConnectionForm}
          onToggle={(connection) =>
            action(async () => {
              await api(
                `/connections/${connection.id}`,
                { enabled: !connection.enabled },
                "PATCH",
              );
              setNotice(
                connection.enabled
                  ? "連線已停用；不會發出新的模型請求。"
                  : "連線已啟用。",
              );
            })
          }
          onVerify={(connection) =>
            action(async () => {
              await api(`/connections/${connection.id}/verify`, {});
              setNotice("金鑰已驗證，未發出模型生成請求。");
            })
          }
          onSync={(connection) =>
            action(async () => {
              await api(`/connections/${connection.id}/sync?force=true`, {});
              setNotice("模型目錄已更新。");
            })
          }
        />
      )}
      {addConnectionId !== null && (
        <AddModelFlow
          initialConnectionId={addConnectionId}
          connections={connections}
          models={models}
          types={types}
          onRefresh={reload}
          onClose={() => setAddConnectionId(null)}
          onManageConnection={(id) => {
            setAddConnectionId(null);
            openConnection(id);
          }}
          onCreated={async (ids, message) => {
            await reload();
            setAddConnectionId(null);
            setTab("models");
            setHighlightId(ids[0] || "");
            setNotice(message);
          }}
        />
      )}
      {connectionForm && (
        <div
          className="mm-flow-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setConnectionForm(null);
          }}
        >
          <section
            ref={connectionFormRef}
            className="mm-connection-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mm-connection-form-title"
          >
            <div className="mm-flow-head">
              <div>
                <small>廠商連線</small>
                <h2 id="mm-connection-form-title">
                  {connectionForm === "new" ? "新增廠商連線" : "編輯連線"}
                </h2>
              </div>
              <button
                className="mm-icon-button"
                aria-label="關閉連線表單"
                onClick={() => setConnectionForm(null)}
              >
                <X size={20} />
              </button>
            </div>
            <div className="mm-dialog-body">
              <ConnectionForm
                key={connectionForm === "new" ? "new" : connectionForm.id}
                initial={connectionForm === "new" ? null : connectionForm}
                types={types}
                onCancel={() => setConnectionForm(null)}
                onSaved={async (saved) => {
                  await reload();
                  const created = connectionForm === "new";
                  setConnectionForm(null);
                  if (created) setAddConnectionId(saved.id);
                  else
                    setNotice(
                      "連線已保存。若更換 OpenRouter 金鑰，請重新驗證。",
                    );
                }}
              />
            </div>
          </section>
        </div>
      )}
      {trial && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !busy) closeTrial();
          }}
        >
          <section
            ref={trialRef}
            className="modal trial-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mm-trial-title"
          >
            <div className="modal-head">
              <h2 id="mm-trial-title">試跑 {trial.name}</h2>
              <button
                className="mm-icon-button"
                disabled={busy}
                aria-label="關閉試跑"
                onClick={closeTrial}
              >
                <X size={20} />
              </button>
            </div>
            <p>
              {trial.provider === "demo"
                ? "此模型提供固定示範回答，不產生 API 費用。"
                : `將發送一筆「Reply OK」短請求，輸出上限為 ${trial.max_output_tokens.toLocaleString()} tokens（含可能的推理）；這是上限，實際用量可能較少，但可能產生 API 費用。這次試跑不加入正式測試紀錄。`}
            </p>
            {trial.provider !== "demo" && (
              <p className="mm-trial-effort">
                思考程度：{trial.reasoning_effort || "模型預設"}
              </p>
            )}
            <label className="mm-trial-timeout">
              網路等待逾時（秒）
              <input
                type="number"
                min="5"
                max="600"
                step="1"
                required
                value={trialTimeout}
                disabled={busy}
                onChange={(event) => setTrialTimeout(event.target.value)}
              />
              <small>單次連線或讀寫等待上限，預設 600 秒；整次試跑可能花更久。</small>
            </label>
            {trialResult?.status === "success" && (
              <div className="mm-trial-result success" role="status">
                <strong>
                  {trialResult.response.output.trim()
                    ? "試跑成功：模型已回應"
                    : "請求成功，但模型回應為空白"}
                </strong>
                <span>
                  這只確認模型可連線並回傳內容，不代表回答品質通過評分。
                </span>
                <div className="mm-trial-meta">
                  <span>回應時間 {trialResult.response.latency_ms} ms</span>
                  {trial.provider !== "demo" && (
                    <span>
                      本次費用{" "}
                      {trialResult.response.cost == null
                        ? "未知"
                        : `$${trialResult.response.cost}`}
                    </span>
                  )}
                  {trialResult.response.upstream_provider && (
                    <span>服務商 {trialResult.response.upstream_provider}</span>
                  )}
                </div>
                <pre className="mm-trial-output">
                  {trialResult.response.output || "（空白回應）"}
                </pre>
              </div>
            )}
            {trialResult?.status === "error" && (
              <div className="mm-trial-result error" role="alert">
                <strong>試跑失敗</strong>
                <span>{trialResult.message}</span>
              </div>
            )}
            <div className="inline-actions">
              <button
                className="secondary"
                disabled={busy}
                onClick={closeTrial}
              >
                {trialResult ? "關閉" : "取消"}
              </button>
              <button
                className="primary"
                disabled={busy || !validTrialTimeout(trialTimeout)}
                onClick={runTrial}
              >
                {busy ? "試跑中…" : trialResult ? "重新試跑" : "開始試跑"}
              </button>
            </div>
          </section>
        </div>
      )}
      {deletingModel && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !busy)
              setDeletingModel(null);
          }}
        >
          <section
            ref={deleteRef}
            className="modal trial-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mm-delete-title"
          >
            <div className="modal-head">
              <h2 id="mm-delete-title">刪除 {deletingModel.name}？</h2>
              <button
                className="mm-icon-button"
                disabled={busy}
                aria-label="關閉刪除確認"
                onClick={() => setDeletingModel(null)}
              >
                <X size={20} />
              </button>
            </div>
            <p>
              模型會從管理清單移除，且不能再建立新測試或重跑使用此模型的歷史失敗項目。既有測試紀錄與結果會保留。
            </p>
            {error && (
              <div className="management-message error" role="alert">
                {error}
              </div>
            )}
            <div className="inline-actions">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => setDeletingModel(null)}
              >
                取消
              </button>
              <button
                className="primary mm-danger-fill"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    await api(
                      `/models/${deletingModel.id}`,
                      undefined,
                      "DELETE",
                    );
                    setDeletingModel(null);
                    setNotice("模型已從管理清單移除，歷史測試紀錄仍保留。");
                  })
                }
              >
                {busy ? "刪除中…" : "確認刪除"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
