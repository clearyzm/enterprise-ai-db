/**
 * Authentication state management using Zustand.
 * 
 * Features:
 * - Persistent storage (localStorage)
 * - Token management (access + refresh)
 * - User profile caching
 * - Hydration handling for SSR
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// ============================================================================
// Types
// ============================================================================

export interface User {
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
}

export interface AuthState {
  // State
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  isHydrated: boolean;

  // Actions
  setTokens: (accessToken: string, refreshToken: string) => void;
  setUser: (user: User) => void;
  clearAuth: () => void;
  setHydrated: () => void;
}

// ============================================================================
// Store
// ============================================================================

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      // Initial state
      accessToken: null,
      refreshToken: null,
      user: null,
      isHydrated: false,

      // Set tokens (after login or refresh)
      setTokens: (accessToken: string, refreshToken: string) => {
        set({ accessToken, refreshToken });
      },

      // Set user profile
      setUser: (user: User) => {
        set({ user });
      },

      // Clear all auth state (logout or refresh failure)
      clearAuth: () => {
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
        });
      },

      // Mark store as hydrated (after rehydration from localStorage)
      setHydrated: () => {
        set({ isHydrated: true });
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        // Only persist tokens and user, not hydration flag
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        // Mark as hydrated after rehydration completes
        state?.setHydrated();
      },
    }
  )
);

// ============================================================================
// Selectors (for performance optimization)
// ============================================================================

/**
 * Check if user is authenticated (has valid tokens)
 */
export const selectIsAuthenticated = (state: AuthState): boolean => {
  return state.accessToken !== null && state.refreshToken !== null;
};

/**
 * Check if user is tenant admin
 */
export const selectIsTenantAdmin = (state: AuthState): boolean => {
  return state.user?.is_tenant_admin ?? false;
};

/**
 * Get user's primary department
 */
export const selectPrimaryDepartment = (state: AuthState) => {
  return state.user?.departments.find((dept) => dept.is_primary) ?? null;
};

/**
 * Get user's role names
 */
export const selectRoleNames = (state: AuthState): string[] => {
  return state.user?.roles.map((role) => role.role_name) ?? [];
};

/**
 * Check if user has specific role
 */
export const selectHasRole = (state: AuthState, roleName: string): boolean => {
  return state.user?.roles.some((role) => role.role_name === roleName) ?? false;
};
