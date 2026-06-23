export type ApiErrorPayload = {
  error?: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
};

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;

  constructor(message: string, code: string, status: number, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

const API_BASE = "/api";

export async function apiRequest<T>(
  path: string,
  init: RequestInit & { body?: BodyInit | object | null } = {}
): Promise<T> {
  const headers = new Headers(init.headers);
  let body = init.body;

  if (body && typeof body === "object" && !(body instanceof FormData) && !(body instanceof Blob)) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    body: body as BodyInit | null | undefined
  });

  if (!response.ok) {
    const payload = (await safeJson(response)) as ApiErrorPayload;
    const error = payload.error;
    throw new ApiError(
      error?.message ?? `Request failed with status ${response.status}`,
      error?.code ?? "request_failed",
      response.status,
      error?.details
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

async function safeJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

export function websocketUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${API_BASE}${path}`;
}
