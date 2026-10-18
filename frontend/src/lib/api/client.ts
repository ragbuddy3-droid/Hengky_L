export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1';

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

type Query = Record<string, string | number | undefined | null>;

function buildUrl(path: string, query?: Query) {
  const url = new URL(`${API_BASE_URL}${path}`);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function parseError(res: Response): Promise<ApiError> {
  const text = await res.text();
  let message = `Terjadi kesalahan (HTTP ${res.status})`;
  try {
    const json = JSON.parse(text);
    if (typeof json.detail === 'string') message = json.detail;
    else if (Array.isArray(json.detail)) message = json.detail.map((d: { msg?: string }) => d.msg).join(', ');
  } catch {
    if (text) message = text;
  }
  return new ApiError(message, res.status);
}

export async function request<T>(
  path: string,
  init: Omit<RequestInit, 'body'> & { query?: Query; json?: unknown; body?: BodyInit } = {},
): Promise<T> {
  const { query, json, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), {
      // Sesi login & tamu disimpan backend sebagai cookie httpOnly.
      credentials: 'include',
      ...rest,
      headers: json !== undefined ? { 'Content-Type': 'application/json', ...headers } : headers,
      body: json !== undefined ? JSON.stringify(json) : init.body,
    });
  } catch {
    throw new ApiError('Tidak dapat terhubung ke server. Pastikan backend berjalan.', 0);
  }
  if (!res.ok) throw await parseError(res);
  return res.json() as Promise<T>;
}
