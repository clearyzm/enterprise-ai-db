/**
 * API client with automatic token refresh and request retry.
 * 
 * Features:
 * - Automatic Authorization header injection
 * - 401 interception → refresh token → retry original request
 * - Refresh failure → clear auth store → redirect to login
 * - TypeScript strict mode compliant
 * 
 * ⚠️ SIMPLIFIED IMPLEMENTATION (Phase 9 v1):
 * - ❌ Does NOT implement request queue (pause requests during token refresh)
 * - ❌ Does NOT implement request cancellation (cancel on component unmount)
 * - ❌ Does NOT implement automatic retry on network errors
 * - ✅ Only implements: 401 interception + token refresh + single retry
 * 
 * ⚠️ DEPENDENCY WARNING:
 * - Backend `/auth/refresh` endpoint is NOT implemented in Phase 2 (returns "not_implemented")
 * - Token refresh logic will fail until backend Phase 3+ implements the endpoint
 * - Current behavior: token expires → user must re-login
 * 
 * TODO (Phase 10+):
 * - Add request queue to prevent concurrent refresh
 * - Add request cancellation with AbortController
 * - Add exponential backoff retry for network errors
 */

import { useAuthStore } from './store/auth';

// ============================================================================
// Types
// ============================================================================

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiResponse<T> {
  data?: T;
  error?: ApiError;
}

// ============================================================================
// Configuration
// ============================================================================

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

// ============================================================================
// Token Refresh Logic
// ============================================================================

let isRefreshing = false;
let refreshPromise: Promise<string> | null = null;

/**
 * Refresh access token using refresh token.
 * 
 * Uses singleton pattern to prevent concurrent refresh requests.
 * If refresh fails, clears auth store and throws error.
 * 
 * @returns New access token
 * @throws Error if refresh fails
 */
async function refreshAccessToken(): Promise<string> {
  // If already refreshing, return existing promise
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }

  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const { refreshToken } = useAuthStore.getState();
      
      if (!refreshToken) {
        throw new Error('No refresh token available');
      }

      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        throw new Error('Token refresh failed');
      }

      const data = await response.json();
      
      // Update auth store with new tokens
      useAuthStore.getState().setTokens(data.access_token, data.refresh_token);
      
      return data.access_token;
    } catch (error) {
      // Refresh failed - clear auth and redirect to login
      useAuthStore.getState().clearAuth();
      
      // Only redirect if we're in browser context
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
      
      throw error;
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

// ============================================================================
// Request Helper
// ============================================================================

interface RequestOptions extends RequestInit {
  skipAuth?: boolean;
  retryOn401?: boolean;
}

/**
 * Make authenticated API request with automatic token refresh.
 * 
 * @param endpoint - API endpoint (e.g., '/datasets')
 * @param options - Fetch options with additional flags
 * @returns Response object
 */
async function request(
  endpoint: string,
  options: RequestOptions = {}
): Promise<Response> {
  const {
    skipAuth = false,
    retryOn401 = true,
    headers = {},
    ...fetchOptions
  } = options;

  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;

  // Build headers
  const requestHeaders: HeadersInit = {
    'Content-Type': 'application/json',
    ...headers,
  };

  // Add Authorization header if not skipped
  if (!skipAuth) {
    const { accessToken } = useAuthStore.getState();
    if (accessToken) {
      requestHeaders['Authorization'] = `Bearer ${accessToken}`;
    }
  }

  // Make request
  const response = await fetch(url, {
    ...fetchOptions,
    headers: requestHeaders,
  });

  // Handle 401 Unauthorized
  if (response.status === 401 && retryOn401 && !skipAuth) {
    try {
      // Refresh token
      const newAccessToken = await refreshAccessToken();
      
      // Retry original request with new token
      const retryHeaders: HeadersInit = {
        ...requestHeaders,
        'Authorization': `Bearer ${newAccessToken}`,
      };

      return fetch(url, {
        ...fetchOptions,
        headers: retryHeaders,
      });
    } catch (error) {
      // Refresh failed, return original 401 response
      return response;
    }
  }

  return response;
}

// ============================================================================
// Convenience Methods
// ============================================================================

/**
 * GET request
 */
export async function get<T>(
  endpoint: string,
  options?: RequestOptions
): Promise<T> {
  const response = await request(endpoint, {
    method: 'GET',
    ...options,
  });

  if (!response.ok) {
    const error = await parseError(response);
    throw error;
  }

  return response.json();
}

/**
 * POST request
 */
export async function post<T>(
  endpoint: string,
  body?: unknown,
  options?: RequestOptions
): Promise<T> {
  const response = await request(endpoint, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
    ...options,
  });

  if (!response.ok) {
    const error = await parseError(response);
    throw error;
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

/**
 * PATCH request
 */
export async function patch<T>(
  endpoint: string,
  body?: unknown,
  options?: RequestOptions
): Promise<T> {
  const response = await request(endpoint, {
    method: 'PATCH',
    body: body ? JSON.stringify(body) : undefined,
    ...options,
  });

  if (!response.ok) {
    const error = await parseError(response);
    throw error;
  }

  return response.json();
}

/**
 * PUT request
 */
export async function put<T>(
  endpoint: string,
  body?: unknown,
  options?: RequestOptions
): Promise<T> {
  const response = await request(endpoint, {
    method: 'PUT',
    body: body ? JSON.stringify(body) : undefined,
    ...options,
  });

  if (!response.ok) {
    const error = await parseError(response);
    throw error;
  }

  return response.json();
}

/**
 * DELETE request
 */
export async function del<T>(
  endpoint: string,
  options?: RequestOptions
): Promise<T> {
  const response = await request(endpoint, {
    method: 'DELETE',
    ...options,
  });

  if (!response.ok) {
    const error = await parseError(response);
    throw error;
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// ============================================================================
// Error Handling
// ============================================================================

/**
 * Parse error response from API.
 * 
 * @param response - Failed response object
 * @returns ApiError object
 */
async function parseError(response: Response): Promise<ApiError> {
  try {
    const data = await response.json();
    
    return {
      code: data.code || `http_${response.status}`,
      message: data.message || data.detail || response.statusText,
      details: data.details,
    };
  } catch {
    // Failed to parse JSON, return generic error
    return {
      code: `http_${response.status}`,
      message: response.statusText || 'An error occurred',
    };
  }
}

// ============================================================================
// Export default API object
// ============================================================================

const api = {
  get,
  post,
  patch,
  put,
  delete: del,
  request,
};

export default api;
