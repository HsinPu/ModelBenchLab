export type Model = {
  id: string;
  name: string;
  provider: string;
  model: string;
  endpoint: string;
  has_key: boolean;
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
    evaluation: { passed: boolean | null; reason: string; error?: boolean };
  };
};
export type Detail = Run & {
  snapshot: { cases: Case[]; prompt: Prompt; settings: { repeats: number } };
  items: Item[];
  reviews: { item_id: string; score: number; note: string }[];
};
export async function api<T>(path: string, data?: unknown): Promise<T> {
  const r = await fetch(
    "/api" + path,
    data === undefined
      ? {}
      : {
          method: "POST",
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
