const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  status: number;
  timestamp?: string;

  constructor(status: number, message: string, timestamp?: string) {
    super(message);
    this.status = status;
    this.timestamp = timestamp;
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    // Khớp format GlobalExceptionHandler.java: { timestamp, message }
    let body: { message?: string; timestamp?: string } = {};
    try {
      body = await res.json();
    } catch {
      // response không phải JSON (vd lỗi mạng/proxy) — bỏ qua, dùng message mặc định
    }
    throw new ApiError(res.status, body.message ?? `Lỗi không xác định (HTTP ${res.status})`, body.timestamp);
  }

  // 204 No Content (vd PATCH config) không có body để parse
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
};
