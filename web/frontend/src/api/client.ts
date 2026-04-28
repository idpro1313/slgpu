import type { Healthz } from "@/api/types";
import { publishMissingStackParams } from "@/stackErrorBus";

const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  code?: string;
  keys?: string[];
  scope?: string;
  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function parseErrorResponse(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return await response.text();
  }
}

function errorMessage(status: number, detail: unknown): string {
  return typeof detail === "object" &&
    detail &&
    "detail" in detail &&
    typeof (detail as { detail: unknown }).detail === "string"
    ? (detail as { detail: string }).detail
    : `HTTP ${status}`;
}

function throwWithStackDetails(
  status: number,
  detail: unknown,
): never {
  const err = new ApiError(status, detail, errorMessage(status, detail));
  if (
    status === 409 &&
    typeof detail === "object" &&
    detail !== null &&
    (detail as { error?: string }).error === "missing_stack_params"
  ) {
    const o = detail as { keys?: string[]; scope?: string; detail?: string };
    err.code = "missing_stack_params";
    err.keys = Array.isArray(o.keys) ? o.keys : undefined;
    err.scope = typeof o.scope === "string" ? o.scope : undefined;
    if (err.keys?.length) {
      publishMissingStackParams({
        keys: err.keys,
        scope: err.scope ?? "",
        detail: typeof o.detail === "string" ? o.detail : undefined,
      });
    }
  }
  throw err;
}

function _isFormData(body: BodyInit | null | undefined): boolean {
  return typeof FormData !== "undefined" && body instanceof FormData;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type") && !_isFormData(init.body)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throwWithStackDetails(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Корневые пути вне `/api/v1` (например `/healthz` для dev-proxy). */
async function requestRoot<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throwWithStackDetails(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, init?: RequestInit) =>
    request<T>(path, { ...init, method: "GET" }),
  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      ...init,
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  /** multipart/form-data — тело передать как `FormData` (без JSON). */
  postForm: <T>(path: string, body: FormData, init?: RequestInit) =>
    request<T>(path, { ...init, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      ...init,
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  delete: <T>(path: string, init?: RequestInit) =>
    request<T>(path, { ...init, method: "DELETE" }),
  healthz: (init?: RequestInit) => requestRoot<Healthz>("/healthz", init),
};
