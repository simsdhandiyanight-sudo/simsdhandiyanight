const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly data: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

let csrfPromise: Promise<string> | undefined;

const ensureCsrfToken = async (): Promise<string> => {
  csrfPromise ??= fetch(`${API_BASE}/auth/csrf/`, {
    credentials: 'include',
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new ApiError('Unable to initialize secure session.', response.status, 'CSRF_ERROR', undefined);
      }
      const data: unknown = await response.json();
      if (
        typeof data !== 'object'
        || data === null
        || !('csrfToken' in data)
        || typeof data.csrfToken !== 'string'
      ) {
        throw new ApiError('Unable to initialize secure session.', response.status, 'CSRF_ERROR', undefined);
      }
      return data.csrfToken;
    })
    .catch((error: unknown) => {
      if (error instanceof ApiError) throw error;
      throw new ApiError('Unable to initialize secure session.', 0, 'NETWORK_ERROR', undefined);
    })
    .finally(() => {
      csrfPromise = undefined;
    });
  return csrfPromise;
};

const responseData = async (response: Response): Promise<unknown> => {
  if (response.status === 204) return undefined;
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) return undefined;
  return response.json();
};

const errorMessage = (status: number, data: unknown): { message: string; code: string } => {
  if (typeof data === 'object' && data !== null && 'error' in data) {
    const error = data.error;
    if (typeof error === 'object' && error !== null) {
      const message = 'message' in error && typeof error.message === 'string' ? error.message : '';
      const code = 'code' in error && typeof error.code === 'string' ? error.code : 'REQUEST_ERROR';
      const details = 'details' in error ? error.details : undefined;
      if (typeof details === 'object' && details !== null) {
        const messages = Object.entries(details).flatMap(([field, value]) => {
          const list = Array.isArray(value) ? value : [value];
          return list.filter((item): item is string => typeof item === 'string').map((item) => `${field}: ${item}`);
        });
        return { message: messages.length ? messages.join(' ') : message || `Request failed (${status}).`, code };
      }
      return { message: message || `Request failed (${status}).`, code };
    }
  }
  return { message: `Request failed (${status}).`, code: 'REQUEST_ERROR' };
};

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  acceptedErrorStatuses: number[] = [],
): Promise<T> {
  const method = (options.method || 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers.set('X-CSRFToken', await ensureCsrfToken());
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`, {
      ...options,
      method,
      headers,
      credentials: 'include',
    });
  } catch {
    throw new ApiError('Unable to reach the ticketing service. Check the connection and try again.', 0, 'NETWORK_ERROR', undefined);
  }

  const data = await responseData(response);
  if (!response.ok && !acceptedErrorStatuses.includes(response.status)) {
    const failure = errorMessage(response.status, data);
    throw new ApiError(failure.message, response.status, failure.code, data);
  }
  return data as T;
}

export async function apiBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`, {
    credentials: 'include',
  });
  if (!response.ok) {
    const data = await responseData(response);
    const failure = errorMessage(response.status, data);
    throw new ApiError(failure.message, response.status, failure.code, data);
  }
  return response.blob();
}

export const jsonBody = (value: unknown): string => JSON.stringify(value);
