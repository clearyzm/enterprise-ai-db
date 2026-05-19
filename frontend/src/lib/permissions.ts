/**
 * Permission checking utilities for UI-level authorization.
 * 
 * WARNING: These checks are for UI purposes only (hiding buttons, routes, etc.).
 * The backend MUST enforce all permissions. Frontend checks are NOT a security boundary.
 * 
 * Permission model:
 * - Actions: read, write, update, delete, approve, manage
 * - Resources: dataset, record, user, role, department, workflow, approval, ai
 * - Format: "action:resource" (e.g., "read:dataset", "manage:user")
 * 
 * ⚠️ SIMPLIFIED IMPLEMENTATION (Phase 9 v1):
 * - ❌ Does NOT parse `role.scope` field from backend (hardcoded mapping)
 * - ❌ Does NOT support department hierarchy (parent dept access child data)
 * - ❌ Does NOT read user's sensitivity clearance level from profile
 * - ✅ Only supports: hardcoded role-to-permission mapping
 * 
 * TODO (Phase 10+):
 * - Backend should return user's full permission list (e.g., permissions: ["read:dataset", "write:record"])
 * - Frontend should directly check array instead of hardcoded mapping
 * - Add department hierarchy support
 * - Add sensitivity clearance level from user profile
 */

import { User } from '@/lib/store/auth';

// ============================================================================
// Types
// ============================================================================

export type Action = 'read' | 'write' | 'update' | 'delete' | 'approve' | 'manage';
export type Resource = 
  | 'dataset' 
  | 'record' 
  | 'user' 
  | 'role' 
  | 'department' 
  | 'workflow' 
  | 'approval' 
  | 'ai'
  | 'audit';

export type Permission = `${Action}:${Resource}`;

// ============================================================================
// Main Permission Check
// ============================================================================

/**
 * Check if user has a specific permission.
 * 
 * @param user - Current user object (from auth store)
 * @param permission - Permission string (e.g., "read:dataset")
 * @returns true if user has permission
 */
export function can(user: User | null, permission: Permission): boolean {
  if (!user) {
    return false;
  }

  // Tenant admins have all permissions
  if (user.is_tenant_admin) {
    return true;
  }

  // Parse permission
  const [action, resource] = permission.split(':') as [Action, Resource];

  // Check role-based permissions
  return user.roles.some((role) => hasRolePermission(role.role_name, action, resource));
}

/**
 * Check if user has ANY of the specified permissions.
 * 
 * @param user - Current user object
 * @param permissions - Array of permission strings
 * @returns true if user has at least one permission
 */
export function canAny(user: User | null, permissions: Permission[]): boolean {
  return permissions.some((permission) => can(user, permission));
}

/**
 * Check if user has ALL of the specified permissions.
 * 
 * @param user - Current user object
 * @param permissions - Array of permission strings
 * @returns true if user has all permissions
 */
export function canAll(user: User | null, permissions: Permission[]): boolean {
  return permissions.every((permission) => can(user, permission));
}

// ============================================================================
// Role-Based Permission Mapping
// ============================================================================

/**
 * Check if a role has a specific permission.
 * 
 * This is a simplified mapping. In a real system, this should be driven by
 * the role.scope field from the backend.
 * 
 * @param roleName - Role name (e.g., "tenant_admin", "editor")
 * @param action - Action (e.g., "read", "write")
 * @param resource - Resource (e.g., "dataset", "record")
 * @returns true if role has permission
 */
function hasRolePermission(roleName: string, action: Action, resource: Resource): boolean {
  const rolePermissions: Record<string, Permission[]> = {
    // Tenant admin: all permissions
    tenant_admin: [
      'read:dataset', 'write:dataset', 'update:dataset', 'delete:dataset', 'manage:dataset',
      'read:record', 'write:record', 'update:record', 'delete:record',
      'read:user', 'write:user', 'update:user', 'delete:user', 'manage:user',
      'read:role', 'write:role', 'update:role', 'delete:role', 'manage:role',
      'read:department', 'write:department', 'update:department', 'delete:department', 'manage:department',
      'read:workflow', 'write:workflow', 'update:workflow', 'delete:workflow', 'manage:workflow',
      'read:approval', 'approve:approval',
      'read:ai', 'write:ai',
      'read:audit',
    ],

    // Dataset admin: manage datasets and records
    dataset_admin: [
      'read:dataset', 'write:dataset', 'update:dataset', 'delete:dataset', 'manage:dataset',
      'read:record', 'write:record', 'update:record', 'delete:record',
      'read:approval',
    ],

    // Approver: read and approve
    approver: [
      'read:dataset',
      'read:record',
      'read:approval', 'approve:approval',
    ],

    // Editor: read and write
    editor: [
      'read:dataset',
      'read:record', 'write:record', 'update:record',
      'read:approval',
      'read:ai', 'write:ai',
    ],

    // Viewer: read only
    viewer: [
      'read:dataset',
      'read:record',
      'read:approval',
      'read:ai',
    ],
  };

  const permissions = rolePermissions[roleName] || [];
  const targetPermission: Permission = `${action}:${resource}`;
  
  return permissions.includes(targetPermission);
}

// ============================================================================
// Resource-Specific Helpers
// ============================================================================

/**
 * Check if user can manage datasets.
 */
export function canManageDatasets(user: User | null): boolean {
  return can(user, 'manage:dataset');
}

/**
 * Check if user can create records.
 */
export function canCreateRecords(user: User | null): boolean {
  return can(user, 'write:record');
}

/**
 * Check if user can edit records.
 */
export function canEditRecords(user: User | null): boolean {
  return can(user, 'update:record');
}

/**
 * Check if user can delete records.
 */
export function canDeleteRecords(user: User | null): boolean {
  return can(user, 'delete:record');
}

/**
 * Check if user can approve changes.
 */
export function canApprove(user: User | null): boolean {
  return can(user, 'approve:approval');
}

/**
 * Check if user can manage users.
 */
export function canManageUsers(user: User | null): boolean {
  return can(user, 'manage:user');
}

/**
 * Check if user can manage roles.
 */
export function canManageRoles(user: User | null): boolean {
  return can(user, 'manage:role');
}

/**
 * Check if user can manage departments.
 */
export function canManageDepartments(user: User | null): boolean {
  return can(user, 'manage:department');
}

/**
 * Check if user can manage workflows.
 */
export function canManageWorkflows(user: User | null): boolean {
  return can(user, 'manage:workflow');
}

/**
 * Check if user can use AI chat.
 */
export function canUseAI(user: User | null): boolean {
  return can(user, 'read:ai');
}

/**
 * Check if user can view audit logs.
 */
export function canViewAudit(user: User | null): boolean {
  return can(user, 'read:audit');
}

// ============================================================================
// Department-Scoped Permissions
// ============================================================================

/**
 * Check if user belongs to a specific department.
 * 
 * @param user - Current user object
 * @param departmentId - Department UUID
 * @returns true if user is in the department
 */
export function isInDepartment(user: User | null, departmentId: string): boolean {
  if (!user) {
    return false;
  }

  return user.departments.some((dept) => dept.department_id === departmentId);
}

/**
 * Get user's primary department ID.
 * 
 * @param user - Current user object
 * @returns Primary department ID or null
 */
export function getPrimaryDepartmentId(user: User | null): string | null {
  if (!user) {
    return null;
  }

  const primaryDept = user.departments.find((dept) => dept.is_primary);
  return primaryDept?.department_id || null;
}

/**
 * Check if user can access a record based on department.
 * 
 * This is a simplified check. Real implementation should consider:
 * - Dataset owner department
 * - Record department
 * - User's department hierarchy
 * - Cross-department permissions
 * 
 * @param user - Current user object
 * @param recordDepartmentId - Record's department ID
 * @returns true if user can access the record
 */
export function canAccessRecordByDepartment(
  user: User | null,
  recordDepartmentId: string | null
): boolean {
  if (!user) {
    return false;
  }

  // Tenant admins can access all records
  if (user.is_tenant_admin) {
    return true;
  }

  // If record has no department, check if user has general read permission
  if (!recordDepartmentId) {
    return can(user, 'read:record');
  }

  // Check if user is in the record's department
  return isInDepartment(user, recordDepartmentId);
}

// ============================================================================
// Sensitivity-Based Permissions
// ============================================================================

export type SensitivityLevel = 'public' | 'internal' | 'confidential' | 'secret';

/**
 * Check if user can access data at a specific sensitivity level.
 * 
 * This is a placeholder. Real implementation should check:
 * - User's clearance level
 * - Role-based sensitivity access
 * - Dataset-specific permissions
 * 
 * @param user - Current user object
 * @param sensitivity - Data sensitivity level
 * @returns true if user can access data at this level
 */
export function canAccessSensitivity(
  user: User | null,
  sensitivity: SensitivityLevel
): boolean {
  if (!user) {
    return sensitivity === 'public';
  }

  // Tenant admins can access all levels
  if (user.is_tenant_admin) {
    return true;
  }

  // Simplified mapping - real implementation should check user's clearance
  const sensitivityOrder: SensitivityLevel[] = ['public', 'internal', 'confidential', 'secret'];
  const userMaxLevel: SensitivityLevel = 'internal'; // Placeholder - should come from user profile

  const userLevelIndex = sensitivityOrder.indexOf(userMaxLevel);
  const requiredLevelIndex = sensitivityOrder.indexOf(sensitivity);

  return userLevelIndex >= requiredLevelIndex;
}
