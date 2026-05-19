/**
 * Authentication guard component for protecting routes.
 * 
 * Features:
 * - Redirects unauthenticated users to login
 * - Optional permission checking (UI-level only, backend enforces)
 * - Handles hydration to prevent SSR flash
 * - Preserves original URL for post-login redirect
 */

'use client';

import { useEffect, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore, selectIsAuthenticated } from '@/lib/store/auth';

// ============================================================================
// Types
// ============================================================================

interface AuthGuardProps {
  children: ReactNode;
  /**
   * Optional permission check (e.g., "manage:user", "read:dataset").
   * This is UI-level only - backend must enforce actual permissions.
   */
  requires?: string;
  /**
   * Custom fallback component when permission check fails.
   * Defaults to "无权限访问此页面" message.
   */
  fallback?: ReactNode;
}

// ============================================================================
// Component
// ============================================================================

export default function AuthGuard({ children, requires, fallback }: AuthGuardProps) {
  const router = useRouter();
  const pathname = usePathname();
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const isHydrated = useAuthStore((state) => state.isHydrated);
  const user = useAuthStore((state) => state.user);

  useEffect(() => {
    // Wait for hydration to complete
    if (!isHydrated) {
      return;
    }

    // Redirect to login if not authenticated
    if (!isAuthenticated) {
      const redirectUrl = `/login?redirect=${encodeURIComponent(pathname)}`;
      router.replace(redirectUrl);
    }
  }, [isHydrated, isAuthenticated, router, pathname]);

  // Show loading during hydration
  if (!isHydrated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="text-gray-500">加载中...</p>
        </div>
      </div>
    );
  }

  // Don't render if not authenticated (will redirect)
  if (!isAuthenticated) {
    return null;
  }

  // Check permission if required
  if (requires && user) {
    const hasPermission = checkPermission(user, requires);
    
    if (!hasPermission) {
      return (
        fallback || (
          <div className="min-h-screen flex items-center justify-center bg-gray-50">
            <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-8">
              <div className="flex flex-col items-center space-y-4">
                <svg
                  className="h-16 w-16 text-red-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                <h2 className="text-2xl font-bold text-gray-900">无权限访问</h2>
                <p className="text-gray-600 text-center">
                  您没有权限访问此页面。如需访问，请联系管理员。
                </p>
                <button
                  onClick={() => router.back()}
                  className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                >
                  返回上一页
                </button>
              </div>
            </div>
          </div>
        )
      );
    }
  }

  // Render children if authenticated and authorized
  return <>{children}</>;
}

// ============================================================================
// Permission Check Helper
// ============================================================================

/**
 * Check if user has required permission.
 * 
 * This is a simplified UI-level check. The backend must enforce actual permissions.
 * 
 * Permission format: "action:resource" (e.g., "manage:user", "read:dataset")
 * 
 * Special cases:
 * - Tenant admins have all permissions
 * - Role-based check (simplified for now)
 * 
 * @param user - Current user object
 * @param permission - Required permission string
 * @returns true if user has permission
 */
function checkPermission(
  user: {
    is_tenant_admin: boolean;
    roles: Array<{
      role_id: string;
      role_name: string;
      scope: Record<string, unknown>;
    }>;
  },
  permission: string
): boolean {
  // Tenant admins have all permissions
  if (user.is_tenant_admin) {
    return true;
  }

  // Parse permission string
  const [action, resource] = permission.split(':');
  
  if (!action || !resource) {
    console.warn(`Invalid permission format: ${permission}`);
    return false;
  }

  // Check role-based permissions
  // This is a simplified check - real implementation should check role.scope
  const hasRole = user.roles.some((role) => {
    // Map common role names to permissions
    switch (role.role_name) {
      case 'tenant_admin':
        return true; // Already handled above, but keep for clarity
      
      case 'dataset_admin':
        return resource === 'dataset' || resource === 'record';
      
      case 'approver':
        return action === 'approve' || action === 'read';
      
      case 'editor':
        return action === 'read' || action === 'write' || action === 'update';
      
      case 'viewer':
        return action === 'read';
      
      default:
        // For custom roles, check if scope contains the permission
        // This is a placeholder - real implementation should parse role.scope
        return false;
    }
  });

  return hasRole;
}

// ============================================================================
// Export permission checker for use in other components
// ============================================================================

export { checkPermission };
