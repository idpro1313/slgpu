import type { Healthz } from "@/api/types";

const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  status: number;
  detail: unknown;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new ApiError(response.status, detail, errorMessage(response.status, detail));
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
    throw new ApiError(response.status, detail, errorMessage(response.status, detail));
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
