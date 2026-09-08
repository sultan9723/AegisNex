"use client";

import { type ReactNode } from "react";
import { usePermissions, type Permission } from "@/components/providers/PermissionProvider";

// ── Permission Gate (conditional render) ──

type PermissionGateProps = {
  permission?: Permission;
  anyPermission?: Permission[];
  allPermissions?: Permission[];
  minRole?: string;
  fallback?: ReactNode;
  children: ReactNode;
};

export function PermissionGate({
  permission,
  anyPermission,
  allPermissions,
  minRole,
  fallback = null,
  children,
}: PermissionGateProps) {
  const { can, canAny, canAll, role, isAdmin } = usePermissions();

  let visible = isAdmin;

  if (!visible && minRole) {
    const roleLevels: Record<string, number> = {
      auditor: 10,
      read_only: 20,
      operator: 40,
      soc_analyst: 60,
      administrator: 80,
      super_admin: 100,
    };
    const userLevel = roleLevels[role] ?? 0;
    const minLevel = roleLevels[minRole] ?? 0;
    visible = userLevel >= minLevel;
  }

  if (!visible && permission) {
    visible = can(permission);
  }

  if (!visible && anyPermission && anyPermission.length > 0) {
    visible = canAny(...anyPermission);
  }

  if (!visible && allPermissions && allPermissions.length > 0) {
    visible = canAll(...allPermissions);
  }

  if (!visible) return <>{fallback}</>;
  return <>{children}</>;
}

// ── Role Badge ──

export function RoleBadge({ role }: { role: string }) {
  const labels: Record<string, string> = {
    super_admin: "Super Admin",
    administrator: "Administrator",
    soc_analyst: "SOC Analyst",
    operator: "Operator",
    read_only: "Read Only",
    auditor: "Auditor",
  };
  const colors: Record<string, string> = {
    super_admin: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
    administrator: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    soc_analyst: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
    operator: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
    read_only: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
    auditor: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400",
  };

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
        colors[role] ?? "bg-gray-100 text-gray-600"
      }`}
    >
      {labels[role] ?? role}
    </span>
  );
}
