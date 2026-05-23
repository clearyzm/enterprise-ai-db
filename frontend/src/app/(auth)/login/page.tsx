/**
 * Login page with tenant slug, email, and password.
 * 
 * Features:
 * - Form validation with client-side feedback
 * - Auto-redirect if already authenticated
 * - Error handling with user-friendly messages
 * - Loading state during authentication
 * 
 * ⚠️ SIMPLIFIED IMPLEMENTATION (Phase 9 v1):
 * - ❌ Does NOT implement "Remember me" (long-lived refresh token)
 * - ❌ Does NOT implement "Forgot password" flow
 * - ❌ Does NOT implement CAPTCHA (brute-force protection)
 * - ❌ Does NOT implement tenant autocomplete/selector
 * - ✅ Only implements: basic login form + client-side validation
 * 
 * TODO (Phase 10+):
 * - Add "Remember me" checkbox
 * - Add "Forgot password" link and flow
 * - Add CAPTCHA for security
 * - Add tenant autocomplete
 */

'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore, selectIsAuthenticated } from '@/lib/store/auth';
import api from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

interface LoginFormData {
  tenant_slug: string;
  email: string;
  password: string;
}

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: string;
    email: string;
    display_name: string;
    status: string;
    is_tenant_admin: boolean;
    tenant_id: string;
    tenant_slug: string;
    tenant_name: string;
    roles: Array<{
      role_id: string;
      role_name: string;
      scope: Record<string, unknown>;
    }>;
    departments: Array<{
      department_id: string;
      department_name: string;
      is_primary: boolean;
    }>;
    last_login_at: string | null;
  };
}

// ============================================================================
// Component
// ============================================================================

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const isHydrated = useAuthStore((state) => state.isHydrated);
  const { setTokens, setUser } = useAuthStore();

  const [formData, setFormData] = useState<LoginFormData>({
    tenant_slug: '',
    email: '',
    password: '',
  });

  const [errors, setErrors] = useState<Partial<LoginFormData>>({});
  const [apiError, setApiError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);

  // Redirect if already authenticated (after hydration)
  useEffect(() => {
    if (isHydrated && isAuthenticated) {
      const redirect = searchParams.get('redirect') || '/datasets';
      router.replace(redirect);
    }
  }, [isHydrated, isAuthenticated, router, searchParams]);

  // Handle input change
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    
    // Clear field error on change
    if (errors[name as keyof LoginFormData]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }));
    }
    
    // Clear API error on change
    if (apiError) {
      setApiError('');
    }
  };

  // Client-side validation
  const validate = (): boolean => {
    const newErrors: Partial<LoginFormData> = {};

    if (!formData.tenant_slug.trim()) {
      newErrors.tenant_slug = '请输入租户标识';
    } else if (!/^[a-z0-9-]+$/.test(formData.tenant_slug)) {
      newErrors.tenant_slug = '租户标识只能包含小写字母、数字和连字符';
    }

    if (!formData.email.trim()) {
      newErrors.email = '请输入邮箱地址';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = '邮箱格式不正确';
    }

    if (!formData.password) {
      newErrors.password = '请输入密码';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Handle form submit
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate
    if (!validate()) {
      return;
    }

    setIsLoading(true);
    setApiError('');

    try {
      // Call login API (skip auth header)
      const response = await api.post<LoginResponse>(
        '/auth/login',
        formData,
        { skipAuth: true, retryOn401: false }
      );

      // Store tokens and user
      setTokens(response.access_token, response.refresh_token);
      setUser(response.user);

      // Redirect to original destination or home
      const redirect = searchParams.get('redirect') || '/datasets';
      router.replace(redirect);
    } catch (error: unknown) {
      // Handle API error
      if (error && typeof error === 'object' && 'message' in error) {
        setApiError(error.message as string);
      } else {
        setApiError('登录失败，请稍后重试');
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Show loading during hydration
  if (!isHydrated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-gray-500">加载中...</div>
      </div>
    );
  }

  // Don't render login form if already authenticated
  if (isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        {/* Header */}
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            企业 AI 数据库
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            登录到您的账户
          </p>
        </div>

        {/* Form */}
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {/* API Error */}
          {apiError && (
            <div className="rounded-md bg-red-50 p-4">
              <div className="flex">
                <div className="flex-shrink-0">
                  <svg
                    className="h-5 w-5 text-red-400"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>
                <div className="ml-3">
                  <p className="text-sm font-medium text-red-800">{apiError}</p>
                </div>
              </div>
            </div>
          )}

          <div className="space-y-4">
            {/* Tenant Slug */}
            <div>
              <label htmlFor="tenant_slug" className="block text-sm font-medium text-gray-700">
                租户标识
              </label>
              <input
                id="tenant_slug"
                name="tenant_slug"
                type="text"
                autoComplete="organization"
                required
                value={formData.tenant_slug}
                onChange={handleChange}
                className={`mt-1 appearance-none relative block w-full px-3 py-2 border ${
                  errors.tenant_slug ? 'border-red-300' : 'border-gray-300'
                } placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm`}
                placeholder=""
                disabled={isLoading}
              />
              {errors.tenant_slug && (
                <p className="mt-1 text-sm text-red-600">{errors.tenant_slug}</p>
              )}
            </div>

            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                邮箱地址
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={formData.email}
                onChange={handleChange}
                className={`mt-1 appearance-none relative block w-full px-3 py-2 border ${
                  errors.email ? 'border-red-300' : 'border-gray-300'
                } placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm`}
                placeholder=""
                disabled={isLoading}
              />
              {errors.email && (
                <p className="mt-1 text-sm text-red-600">{errors.email}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                密码
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={formData.password}
                onChange={handleChange}
                className={`mt-1 appearance-none relative block w-full px-3 py-2 border ${
                  errors.password ? 'border-red-300' : 'border-gray-300'
                } placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm`}
                placeholder=""
                disabled={isLoading}
              />
              {errors.password && (
                <p className="mt-1 text-sm text-red-600">{errors.password}</p>
              )}
            </div>
          </div>

          {/* Submit Button */}
          <div>
            <button
              type="submit"
              disabled={isLoading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? '登录中...' : '登录'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
