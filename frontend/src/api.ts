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
  reasoning_effort?: ReasoningEffort | null;
  max_output_tokens: number;
  catalog?: CatalogDetails | null;
};
export type ReasoningEffort = "low" | "medium" | "high" | "xhigh" | "max" | "ultra";
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
export type ProviderType = {
  id: string;
  label: string;
  description: string;
  supports_catalog: boolean;
  verification: "metadata" | "model_trial";
  requires_api_key: boolean;
  requires_endpoint: boolean;
  fixed_endpoint: string | null;
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
  kind: "manual" | "exact" | "contains" | "choice" | "json_schema";
  expected?: string;
  schema?: Record<string, unknown>;
};
export type Case = {
  title: string;
  messages: { role: "user" | "assistant"; content: string }[];
  rule: Rule;
  tags?: string[];
  source?: {
    dataset: string;
    revision: string;
    subject: string;
    split: string;
    row: number;
    url: string;
    license: string;
    imported_from: string;
  } | null;
};
export type Dataset = {
  id: string;
  name: string;
  cases: Case[];
  case_count?: number;
  bundle_id?: string | null;
  bundle_name?: string | null;
  bundle_index?: number | null;
  bundle_total?: number | null;
};
export type Prompt = { id: string; name: string; text: string };
export type CostSummary = {
  reported_usd: string;
  reported_items: number;
  unknown_items: number;
  by_model: Record<string, {
    reported_usd: string;
    reported_items: number;
    unknown_items: number;
  }>;
};
export type Run = {
  id: string;
  batch_id?: string | null;
  name: string;
  status: string;
  created_at: string;
  total: number;
  counts: Record<string, number>;
  passed: number;
  graded: number;
  pass_rate: number | null;
  avg_latency_ms: number | null;
  cost_summary: CostSummary;
  models: Model[];
  dataset_name: string;
};
export type Ranking = {
  run_id: string;
  batch_id: string | null;
  name: string;
  dataset_name: string;
  run_count: number;
  is_final: boolean;
  status: string;
  models: {
    model_id: string;
    name: string;
    provider: string;
    dynamic_model: boolean;
    total: number;
    completed: number;
    failed: number;
    cancelled: number;
    graded: number;
    passed: number;
    pass_rate: number | null;
  }[];
};
export type DatasetRanking = {
  dataset_name: string;
  question_count: number;
  is_final: boolean;
  models: (Ranking["models"][number] & {
    provisional: boolean;
    cancelled_run: boolean;
    ranked: boolean;
  })[];
};
export type Item = {
  id: string;
  model_id: string;
  case_index: number;
  repeat_index: number;
  status: string;
  attempts: {
    error?: string;
    code?: string;
    status: string;
    diagnostics?: {
      finish_reason?: string;
      http_status?: number;
      requested_max_tokens?: number | null;
      completion_tokens?: number | null;
      reasoning_tokens?: number | null;
      resolved_model?: string | null;
      elapsed_ms?: number;
      timeout_kind?: string;
      configured_timeout_seconds?: number;
      reported_cost_usd?: string | null;
    };
  }[];
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
    cost_source?: string | null;
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
  method = data === undefined ? "GET" : "POST",
  signal?: AbortSignal,
): Promise<T> {
  const r = await fetch("/api" + path, {
    method,
    signal,
    ...(data === undefined
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        }),
  });
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
