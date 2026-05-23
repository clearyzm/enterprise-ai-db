/**
 * Main application layout with authentication guard.
 * 
 * Features:
 * - Wraps all authenticated pages
 * - Provides sidebar navigation
 * - Top bar with user menu
 * - TanStack Query provider
 * - Future: WebSocket provider for real-time updates
 * 
 * ⚠️ SIMPLIFIED IMPLEMENTATION (Phase 9 v1):
 * - ❌ Does NOT implement sidebar collapse/expand (mobile adaptation)
 * - ❌ Does NOT implement user menu dropdown (click to expand)
 * - ❌ Does NOT implement notification center (approval reminders)
 * - ❌ Does NOT implement global search (cross-dataset search)
 * - ❌ Does NOT implement WebSocket provider (no real-time updates)
 * - ✅ Only implements: fixed sidebar + basic navigation
 * 
 * TODO (Phase 10+):
 * - Add sidebar collapse for mobile (< 768px)
 * - Add WebSocket provider for real-time data sync
 * - Add notification center
 * - Add global search
 */

'use client';

import { ReactNode } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import AuthGuard from '@/components/auth-guard';
import { useAuthStore } from '@/lib/store/auth';
import { 
  canManageDatasets, 
  canManageUsers, 
  canApprove, 
  canUseAI,
  canViewAudit 
} from '@/lib/permissions';

// ============================================================================
// Query Client Setup
// ============================================================================

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// ============================================================================
// Layout Component
// ============================================================================

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthGuard>
        <AppLayoutInner>{children}</AppLayoutInner>
      </AuthGuard>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}

// ============================================================================
// Inner Layout (after auth check)
// ============================================================================

function AppLayoutInner({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const clearAuth = useAuthStore((state) => state.clearAuth);

  // Handle logout
  const handleLogout = () => {
    clearAuth();
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 w-64 bg-white border-r border-gray-200">
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center h-16 px-6 border-b border-gray-200">
            <h1 className="text-xl font-bold text-gray-900">企业 AI 数据库</h1>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-4 py-6 space-y-1 overflow-y-auto">
            {/* Datasets */}
            <NavLink href="/datasets" active={pathname.startsWith('/datasets')}>
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
              </svg>
              <span>数据集</span>
            </NavLink>

            {/* Approvals */}
            {canApprove(user) && (
              <NavLink href="/approvals" active={pathname.startsWith('/approvals')}>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>审批</span>
              </NavLink>
            )}

            {/* AI Chat */}
            {canUseAI(user) && (
              <NavLink href="/ai" active={pathname.startsWith('/ai')}>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                <span>AI 助手</span>
              </NavLink>
            )}

            {/* Divider */}
            {(canManageUsers(user) || canManageDatasets(user) || canViewAudit(user)) && (
              <div className="pt-4 pb-2">
                <div className="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  管理
                </div>
              </div>
            )}

            {/* Admin - Users */}
            {canManageUsers(user) && (
              <NavLink href="/users" active={pathname.startsWith('/users')}>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
                <span>用户管理</span>
              </NavLink>
            )}

            {/* Admin - Roles */}
            {canManageUsers(user) && (
              <NavLink href="/roles" active={pathname.startsWith('/roles')}>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                </svg>
                <span>角色管理</span>
              </NavLink>
            )}

            {/* Admin - Departments */}
            {canManageUsers(user) && (
              <NavLink href="/departments" active={pathname.startsWith('/departments')}>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                <span>部门管理</span>
              </NavLink>
            )}

            {/* Audit Log */}
            {canViewAudit(user) && (
              <NavLink href="/audit" active={pathname.startsWith('/audit')}>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span>审计日志</span>
              </NavLink>
            )}
          </nav>

          {/* User Menu */}
          <div className="border-t border-gray-200 p-4">
            <div className="flex items-center space-x-3">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center text-white font-semibold">
                  {user?.display_name.charAt(0).toUpperCase()}
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {user?.display_name}
                </p>
                <p className="text-xs text-gray-500 truncate">
                  {user?.email}
                </p>
              </div>
            </div>
            <div className="mt-3 space-y-1">
              <button
                onClick={() => router.push('/change-password')}
                className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md"
              >
                修改密码
              </button>
              <button
                onClick={handleLogout}
                className="w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-md"
              >
                退出登录
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="pl-64">
        <div className="min-h-screen">
          {children}
        </div>
      </main>
    </div>
  );
}

// ============================================================================
// Navigation Link Component
// ============================================================================

interface NavLinkProps {
  href: string;
  active: boolean;
  children: ReactNode;
}

function NavLink({ href, active, children }: NavLinkProps) {
  return (
    <Link
      href={href}
      className={`flex items-center space-x-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
        active
          ? 'bg-blue-50 text-blue-600'
          : 'text-gray-700 hover:bg-gray-100 hover:text-gray-900'
      }`}
    >
      {children}
    </Link>
  );
}
