import type {
  Action,
  ActionBody,
  ActionResponse,
  BatchResponse,
  EventItem,
  ReceiptDetail,
  ReceiptList,
  RevisionDetail,
  SubmitResponse,
} from "./types";

const BASE = "/api";

export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ApiErrorBody,
  ) {
    super(body.message);
  }
  get code(): string {
    return this.body.code;
  }
}

function toApiError(status: number, data: unknown): ApiError {
  const raw = (data as { error?: ApiErrorBody } | null)?.error;
  if (raw) return new ApiError(status, raw);
  // FastAPI's own validation shape, in case a route is reached without the handler.
  const detail = (data as { detail?: { msg: string; loc: unknown[] }[] } | null)?.detail;
  const message = Array.isArray(detail)
    ? detail.map((d) => `${d.loc.join(".")}: ${d.msg}`).join("; ")
    : `The server answered ${status}`;
  return new ApiError(status, { code: "invalid_request", message, details: {} });
}

async function request<T>(
  path: string,
  init: RequestInit & { allow?: number[] } = {},
): Promise<{ status: number; data: T }> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch {
    throw new ApiError(0, {
      code: "unreachable",
      message: "Cannot reach the server. Check that the API is running.",
      details: {},
    });
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok && !(init.allow ?? []).includes(res.status)) throw toApiError(res.status, data);
  return { status: res.status, data: data as T };
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export interface ListQuery {
  state?: string;
  disposition?: string;
  batch_id?: string;
  limit?: number;
  offset?: number;
}

export const api = {
  health: () => request<{ status: string; schema_version: number }>("/health").then((r) => r.data),

  listReceipts: (q: ListQuery = {}) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== "") params.set(k, String(v));
    const qs = params.toString();
    return request<ReceiptList>(`/receipts${qs ? `?${qs}` : ""}`).then((r) => r.data);
  },

  getReceipt: (id: string) =>
    request<ReceiptDetail>(`/receipts/${encodeURIComponent(id)}`).then((r) => r.data),

  getEvents: (id: string) =>
    request<{ items: EventItem[] }>(`/receipts/${encodeURIComponent(id)}/events`).then(
      (r) => r.data.items,
    ),

  getRevision: (id: string, n: number) =>
    request<RevisionDetail>(`/receipts/${encodeURIComponent(id)}/revisions/${n}`).then(
      (r) => r.data,
    ),

  submitReceipt: (receipt: unknown, idempotencyKey?: string) => {
    const init = json(receipt);
    if (idempotencyKey) {
      (init.headers as Record<string, string>)["Idempotency-Key"] = idempotencyKey;
    }
    return request<SubmitResponse>("/receipts", init).then((r) => r.data);
  },

  submitBatch: (body: string, contentType: "application/x-ndjson" | "application/json") =>
    request<BatchResponse>("/batches", {
      method: "POST",
      headers: { "Content-Type": contentType },
      body,
    }).then((r) => r.data),

  getBatch: (id: string) =>
    request<BatchResponse>(`/batches/${encodeURIComponent(id)}`).then((r) => r.data),

  retry: (id: string) =>
    request<unknown>(`/receipts/${encodeURIComponent(id)}/retry`, { method: "POST" }).then(
      (r) => r.data,
    ),

  act: (id: string, action: Action, body: ActionBody) =>
    request<ActionResponse>(
      `/receipts/${encodeURIComponent(id)}/actions/${action}`,
      json(body),
    ).then((r) => r.data),
};
