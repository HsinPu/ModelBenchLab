import type { Case } from "../../api";

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const MAX_CASES = 1000;
const RULE_KINDS = new Set(["manual", "exact", "contains", "choice", "json_schema"]);

export async function parseDatasetFile(file: File): Promise<Case[]> {
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension !== "csv" && extension !== "json") {
    throw Error("請選擇 JSON 或 CSV 題庫檔案");
  }
  if (file.size > MAX_FILE_BYTES) throw Error("檔案不可超過 5 MB");

  const content = (await file.text()).replace(/^\uFEFF/, "");
  let parsed: unknown;
  if (extension === "csv") {
    const rows = parseCSV(content);
    const headers = (rows.shift() ?? []).map((header) => header.trim());
    if (!["title", "question", "kind", "expected"].every((header) => headers.includes(header))) {
      throw Error("CSV 首列需要 title,question,kind,expected 欄位");
    }
    parsed = rows.map((row, rowIndex) => ({ row, rowIndex })).filter(({ row }) => row.some((cell) => cell.trim())).map(({ row, rowIndex }) => {
      const values = Object.fromEntries(headers.map((header, index) => [header, row[index]?.trim() ?? ""]));
      const kind = values.kind || "contains";
      if (!RULE_KINDS.has(kind)) throw Error(`不支援的評分規則：${kind}`);
      return {
        title: values.title,
        messages: [{ role: "user", content: values.question }],
        rule: { kind, expected: values.expected },
        source: {
          dataset: file.name,
          revision: "",
          subject: "",
          split: "",
          row: rowIndex + 2,
          url: "",
          license: "",
          imported_from: "local_csv",
        },
      };
    });
  } else {
    try {
      const data = JSON.parse(content);
      parsed = Array.isArray(data) ? data : data?.cases;
    } catch {
      throw Error("JSON 格式錯誤，請檢查檔案內容");
    }
  }

  if (!Array.isArray(parsed) || parsed.length < 1 || parsed.length > MAX_CASES) {
    throw Error("檔案需包含 1–1000 題的題目陣列");
  }
  if (!parsed.every((item) =>
    item && typeof item.title === "string" && item.title.trim() &&
    Array.isArray(item.messages) && item.messages.length > 0 &&
    item.messages.every((message: { content?: unknown; role?: unknown }) =>
      (message?.role === "user" || message?.role === "assistant") &&
      typeof message.content === "string" && message.content.trim()) &&
    item.rule && RULE_KINDS.has(item.rule.kind)
  )) {
    throw Error("每題需包含 title、messages 與有效的 rule");
  }
  return parsed as Case[];
}

function parseCSV(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      if (quoted && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else quoted = !quoted;
    } else if (ch === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((ch === "\n" || ch === "\r") && !quoted) {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else cell += ch;
  }
  if (quoted) throw Error("CSV 引號未閉合");
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}
