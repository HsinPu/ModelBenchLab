export type Model = {
  id: string;
  name: string;
  provider: string;
  model: string;
  endpoint: string;
  has_key: boolean;
  connection_id?: string | null;
  connection_name?: string | null;
  enabled?: boolean;
  available?: boolean;
  unavailable_reason?: string;
  catalog?: CatalogDetails | null;
};
export type CatalogDetails = {
  context_length: number | null;
  max_completion_tokens: number | null;
  input_modalities: string[];
  output_modalities: string[];
  supported_parameters: string[];
  pricing: Record<string, string | null>;
  text_compatible: boolean;
  fixed_model: boolean;
};
export type Connection = {
  id: string;
  name: string;
  provider: string;
  endpoint: string;
  enabled: boolean;
  has_key: boolean;
  status: string;
  error: string;
  usage: {
    limit?: number | null;
    limit_remaining?: number | null;
    usage?: number | null;
    is_free_tier?: boolean | null;
  };
  last_checked_at: string | null;
  last_synced_at: string | null;
};
export type CatalogEntry = {
  id: string;
  model_id: string;
  name: string;
  author: string;
  details: CatalogDetails;
  added: boolean;
  free: boolean;
  selectable: boolean;
};
export type CatalogPage = {
  items: CatalogEntry[];
  total: number;
  authors: string[];
  synced_at: string | null;
  error: string;
};
export type Rule = {
  kind: "manual" | "exact" | "contains" | "json_schema";
  expected?: string;
  schema?: Record<string, unknown>;
};
export type Case = {
  title: string;
  messages: { role: "user" | "assistant"; content: string }[];
  rule: Rule;
  tags?: string[];
};
export type Dataset = { id: string; name: string; cases: Case[] };
export type Prompt = { id: string; name: string; text: string };
export type Run = {
  id: string;
  name: string;
  status: string;
  created_at: string;
  total: number;
  counts: Record<string, number>;
  passed: number;
  graded: number;
  pass_rate: number | null;
  avg_latency_ms: number | null;
  models: Model[];
  dataset_name: string;
};
export type Item = {
  id: string;
  model_id: string;
  case_index: number;
  repeat_index: number;
  status: string;
  attempts: { error?: string; status: string }[];
  result: null | {
    output: string;
    latency_ms: number;
    input_tokens: number | null;
    output_tokens: number | null;
    demo: boolean;
    requested_model?: string;
    resolved_model?: string | null;
    upstream_provider?: string | null;
    generation_id?: string | null;
    cost?: string | null;
    credential_version?: number | null;
    evaluation: { passed: boolean | null; reason: string; error?: boolean };
  };
};
export type Detail = Run & {
  snapshot: { cases: Case[]; prompt: Prompt; settings: { repeats: number } };
  items: Item[];
  reviews: { item_id: string; score: number; note: string }[];
};
export async function api<T>(
  path: string,
  data?: unknown,
  method = "POST",
): Promise<T> {
  const r = await fetch(
    "/api" + path,
    data === undefined
      ? {}
      : {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  if (!r.ok) {
    let message = "請求失敗";
    try {
      const b = await r.json();
      message =
        typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch {}
    throw new Error(message);
  }
  return r.json();
}
