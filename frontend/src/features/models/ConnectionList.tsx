import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import type { Connection, Model, ProviderType } from "../../api";
import { connectionStatus, credits, providerFor, stamp } from "./modelUi";
import { useDialogFocus } from "./useDialogFocus";

export default function ConnectionList({
  connections,
  models,
  types,
  focusedId,
  busy,
  onNew,
  onAddModel,
  onEdit,
  onToggle,
  onVerify,
  onSync,
}: {
  connections: Connection[];
  models: Model[];
  types: ProviderType[];
  focusedId: string;
  busy: boolean;
  onNew: () => void;
  onAddModel: (connection: Connection) => void;
  onEdit: (connection: Connection) => void;
  onToggle: (connection: Connection) => void;
  onVerify: (connection: Connection) => void;
  onSync: (connection: Connection) => void;
}) {
  const [detailId, setDetailId] = useState("");
  const dialogRef = useDialogFocus<HTMLElement>(Boolean(detailId), () =>
    setDetailId(""),
  );
  useEffect(() => {
    if (focusedId) setDetailId(focusedId);
  }, [focusedId]);
  const detail = connections.find((connection) => connection.id === detailId);
  const detailType = detail && providerFor(types, detail.provider);

  return (
    <section className="mm-workspace" aria-label="廠商連線">
      <div className="mm-toolbar">
        <div>
          <h2>
            廠商連線 <span className="mm-count">{connections.length}</span>
          </h2>
          <p>一組連線可共用金鑰並加入多個模型。</p>
        </div>
        <button className="primary" onClick={onNew}>
          <Plus size={16} />
          新增連線
        </button>
      </div>
      {!connections.length ? (
        <div className="mm-empty">
          <h3>尚未建立廠商連線</h3>
          <p>選擇服務類型並保存連線，再加入模型。</p>
          <button className="primary" onClick={onNew}>
            建立第一組連線
          </button>
        </div>
      ) : (
        <div className="panel table-wrap mm-connection-table-wrap">
          <table className="mm-connection-table">
            <thead>
              <tr>
                <th>連線</th>
                <th>服務類型</th>
                <th>狀態</th>
                <th>模型</th>
                <th>最近檢查</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {connections.map((connection) => {
                const type = providerFor(types, connection.provider);
                const status = connectionStatus(connection, type);
                return (
                  <tr key={connection.id}>
                    <td data-label="連線">
                      <strong>{connection.name}</strong>
                      {type?.requires_endpoint && (
                        <code>{connection.endpoint}</code>
                      )}
                    </td>
                    <td data-label="服務類型">
                      {type?.label || connection.provider}
                    </td>
                    <td data-label="狀態">
                      <span
                        className={`mm-status ${connection.enabled && (type?.verification !== "metadata" || connection.status === "verified") ? "ready" : "warning"}`}
                      >
                        {status}
                      </span>
                    </td>
                    <td data-label="模型">
                      {
                        models.filter(
                          (model) => model.connection_id === connection.id,
                        ).length
                      }
                    </td>
                    <td data-label="最近檢查">
                      {type?.verification === "metadata"
                        ? stamp(connection.last_checked_at)
                        : "試跑模型檢查"}
                    </td>
                    <td data-label="操作" className="mm-row-actions">
                      <button
                        className="primary"
                        onClick={() => onAddModel(connection)}
                      >
                        加入模型
                      </button>
                      <button
                        className="secondary"
                        onClick={() => setDetailId(connection.id)}
                      >
                        管理
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {detail && (
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
            aria-labelledby="mm-connection-detail-title"
          >
            <div className="mm-drawer-head">
              <div>
                <small>廠商連線</small>
                <h2 id="mm-connection-detail-title">{detail.name}</h2>
              </div>
              <button
                className="mm-icon-button"
                aria-label="關閉連線詳情"
                onClick={() => setDetailId("")}
              >
                <X size={20} />
              </button>
            </div>
            <div className="mm-drawer-body">
              <span
                className={`mm-status ${detail.enabled && (detailType?.verification !== "metadata" || detail.status === "verified") ? "ready" : "warning"}`}
              >
                {connectionStatus(detail, detailType)}
              </span>
              {detail.error && (
                <p className="mm-inline-error">{detail.error}</p>
              )}
              <dl className="mm-detail-list">
                <dt>服務類型</dt>
                <dd>{detailType?.label || detail.provider}</dd>
                <dt>模型數</dt>
                <dd>
                  {
                    models.filter((model) => model.connection_id === detail.id)
                      .length
                  }
                </dd>
                {detailType?.requires_endpoint && (
                  <>
                    <dt>API Base URL</dt>
                    <dd>
                      <code>{detail.endpoint}</code>
                    </dd>
                  </>
                )}
                <dt>API Key</dt>
                <dd>{detail.has_key ? "已加密保存" : "未設定"}</dd>
                {detailType?.verification === "metadata" && (
                  <>
                    <dt>最後驗證</dt>
                    <dd>{stamp(detail.last_checked_at)}</dd>
                    <dt>最後同步</dt>
                    <dd>{stamp(detail.last_synced_at)}</dd>
                  </>
                )}
              </dl>
              {detailType?.verification === "metadata" && (
                <div className="mm-credit-panel">
                  <h3>金鑰額度資訊</h3>
                  <dl className="mm-detail-list">
                    <dt>額度上限</dt>
                    <dd>
                      {detail.usage.limit === null
                        ? "未設限"
                        : credits(detail.usage.limit)}
                    </dd>
                    <dt>剩餘額度</dt>
                    <dd>{credits(detail.usage.limit_remaining)}</dd>
                    <dt>累計用量</dt>
                    <dd>{credits(detail.usage.usage)}</dd>
                  </dl>
                  <p>這是金鑰資訊，不代表帳戶餘額。</p>
                </div>
              )}
            </div>
            <div className="mm-drawer-actions mm-connection-actions">
              <button
                className="primary"
                onClick={() => {
                  setDetailId("");
                  onAddModel(detail);
                }}
              >
                加入模型
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => {
                  setDetailId("");
                  onEdit(detail);
                }}
              >
                編輯 / 更換金鑰
              </button>
              {detailType?.verification === "metadata" && (
                <button
                  className="secondary"
                  disabled={busy || !detail.enabled}
                  onClick={() => onVerify(detail)}
                >
                  驗證金鑰
                </button>
              )}
              {detailType?.supports_catalog && (
                <button
                  className="secondary"
                  disabled={
                    busy ||
                    !detail.enabled ||
                    (detailType.verification === "metadata" &&
                      detail.status !== "verified")
                  }
                  onClick={() => onSync(detail)}
                >
                  更新模型目錄
                </button>
              )}
              <button
                className="secondary"
                disabled={busy}
                onClick={() => onToggle(detail)}
              >
                {detail.enabled ? "停用連線" : "啟用連線"}
              </button>
            </div>
          </aside>
        </div>
      )}
    </section>
  );
}
