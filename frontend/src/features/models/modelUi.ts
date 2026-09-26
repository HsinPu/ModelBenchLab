import type { Connection, Model, ProviderType } from "../../api";

export const providerFor = (types: ProviderType[], id: string) =>
  types.find((type) => type.id === id);

export const connectionReady = (connection: Connection, type?: ProviderType) =>
  connection.enabled &&
  (type?.verification !== "metadata" || connection.status === "verified");

export function connectionStatus(connection: Connection, type?: ProviderType) {
  if (!connection.enabled) return "已停用";
  if (type?.verification === "model_trial") return "可加入模型";
  return (
    {
      verified: "已驗證",
      unverified: "待驗證",
      invalid: "金鑰無效",
      error: "驗證失敗",
    }[connection.status] || connection.status
  );
}

export function modelStatus(
  model: Model,
  connection?: Connection,
  type?: ProviderType,
) {
  if (model.enabled === false)
    return {
      label: "模型已停用",
      detail: "啟用模型後即可使用。",
      tone: "warning",
    };
  if (connection && !connection.enabled)
    return {
      label: "連線已停用",
      detail: "前往廠商連線啟用。",
      tone: "warning",
    };
  if (
    connection &&
    type?.verification === "metadata" &&
    connection.status !== "verified"
  )
    return {
      label: "連線需驗證",
      detail: "前往廠商連線驗證金鑰。",
      tone: "warning",
    };
  if (model.available === false)
    return {
      label: "目前不可用",
      detail: model.unavailable_reason || "請查看模型與連線設定。",
      tone: "warning",
    };
  return { label: "可試跑", detail: "", tone: "ready" };
}

export const stamp = (value: string | null) =>
  value ? new Date(value).toLocaleString("zh-TW") : "尚未檢查";

export const catalogPrice = (value: string | null | undefined) =>
  value == null
    ? "未知"
    : "$" +
      (Number(value) * 1_000_000).toLocaleString("en-US", {
        maximumFractionDigits: 4,
      });

export const credits = (value: number | null | undefined) =>
  value == null
    ? "未提供"
    : "$" + value.toLocaleString("en-US", { maximumFractionDigits: 4 });
