"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useAuth, type User } from "@/lib/auth";

// ── Permission constants (mirrors backend src/rbac.py) ──

export const PERMISSIONS = {
  INCIDENT_READ: "incident:read",
  INCIDENT_WRITE: "incident:write",
  INCIDENT_ACK: "incident:acknowledge",
  INCIDENT_RESOLVE: "incident:resolve",
  INCIDENT_DELETE: "incident:delete",
  MONITORING_READ: "monitoring:read",
  MONITORING_WRITE: "monitoring:write",
  MONITORING_DELETE: "monitoring:delete",
  APIKEY_READ: "apikey:read",
  APIKEY_WRITE: "apikey:write",
  APIKEY_DELETE: "apikey:delete",
  USER_READ: "user:read",
  USER_WRITE: "user:write",
  USER_ADMIN: "user:admin",
  SESSION_READ: "session:read",
  SESSION_REVOKE: "session:revoke",
  ORG_READ: "org:read",
  ORG_WRITE: "org:write",
  ORG_ADMIN: "org:admin",
  SETTINGS_READ: "settings:read",
  SETTINGS_WRITE: "settings:write",
  AUDIT_READ: "audit:read",
  AI_CHAT: "ai:chat",
  AI_PLAN: "ai:plan",
  AI_EXECUTE: "ai:execute",
  NOTIFICATION_READ: "notification:read",
  NOTIFICATION_WRITE: "notification:write",
} as const;

export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];

// ── Role → Permissions mapping ──

const ROLE_PERMISSIONS: Record<string, Permission[]> = {
  super_admin: Object.values(PERMISSIONS) as Permission[],
  administrator: [
    PERMISSIONS.INCIDENT_READ, PERMISSIONS.INCIDENT_WRITE, PERMISSIONS.INCIDENT_ACK,
    PERMISSIONS.INCIDENT_RESOLVE, PERMISSIONS.INCIDENT_DELETE,
    PERMISSIONS.MONITORING_READ, PERMISSIONS.MONITORING_WRITE, PERMISSIONS.MONITORING_DELETE,
    PERMISSIONS.APIKEY_READ, PERMISSIONS.APIKEY_WRITE, PERMISSIONS.APIKEY_DELETE,
    PERMISSIONS.USER_READ, PERMISSIONS.USER_WRITE, PERMISSIONS.USER_ADMIN,
    PERMISSIONS.SESSION_READ, PERMISSIONS.SESSION_REVOKE,
    PERMISSIONS.ORG_READ, PERMISSIONS.ORG_WRITE, PERMISSIONS.ORG_ADMIN,
    PERMISSIONS.SETTINGS_READ, PERMISSIONS.SETTINGS_WRITE,
    PERMISSIONS.AUDIT_READ,
    PERMISSIONS.AI_CHAT, PERMISSIONS.AI_PLAN, PERMISSIONS.AI_EXECUTE,
    PERMISSIONS.NOTIFICATION_READ, PERMISSIONS.NOTIFICATION_WRITE,
  ],
  soc_analyst: [
    PERMISSIONS.INCIDENT_READ, PERMISSIONS.INCIDENT_WRITE, PERMISSIONS.INCIDENT_ACK,
    PERMISSIONS.INCIDENT_RESOLVE,
    PERMISSIONS.MONITORING_READ,
    PERMISSIONS.USER_READ,
    PERMISSIONS.SESSION_READ,
    PERMISSIONS.AI_CHAT, PERMISSIONS.AI_PLAN,
    PERMISSIONS.NOTIFICATION_READ,
  ],
  operator: [
    PERMISSIONS.INCIDENT_READ, PERMISSIONS.INCIDENT_ACK,
    PERMISSIONS.MONITORING_READ,
    PERMISSIONS.AI_CHAT,
    PERMISSIONS.NOTIFICATION_READ,
  ],
  read_only: [
    PERMISSIONS.INCIDENT_READ,
    PERMISSIONS.MONITORING_READ,
    PERMISSIONS.USER_READ,
    PERMISSIONS.NOTIFICATION_READ,
    PERMISSIONS.SETTINGS_READ,
  ],
  auditor: [
    PERMISSIONS.INCIDENT_READ,
    PERMISSIONS.MONITORING_READ,
    PERMISSIONS.USER_READ,
    PERMISSIONS.SESSION_READ,
    PERMISSIONS.AUDIT_READ,
    PERMISSIONS.SETTINGS_READ,
    PERMISSIONS.NOTIFICATION_READ,
  ],
};

// ── Context ──

type PermissionContextValue = {
  permissions: Permission[];
  can: (permission: Permission) => boolean;
  canAny: (...permissions: Permission[]) => boolean;
  canAll: (...permissions: Permission[]) => boolean;
  role: string;
  isAdmin: boolean;
};

const PermissionContext = createContext<PermissionContextValue | null>(null);

export function PermissionProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();

  const value = useMemo<PermissionContextValue>(() => {
    const role = user?.role ?? "read_only";
    const permissions = ROLE_PERMISSIONS[role] ?? ROLE_PERMISSIONS["read_only"];
    const isAdmin = role === "super_admin" || role === "administrator";

    return {
      permissions,
      role,
      isAdmin,
      can: (permission: Permission) => permissions.includes(permission as never) || isAdmin,
      canAny: (...perms: Permission[]) => perms.some((p) => permissions.includes(p as never) || isAdmin),
      canAll: (...perms: Permission[]) => perms.every((p) => permissions.includes(p as never) || isAdmin),
    };
  }, [user]);

  return (
    <PermissionContext.Provider value={value}>
      {children}
    </PermissionContext.Provider>
  );
}

export function usePermissions(): PermissionContextValue {
  const ctx = useContext(PermissionContext);
  if (!ctx) throw new Error("usePermissions must be used within PermissionProvider");
  return ctx;
}
