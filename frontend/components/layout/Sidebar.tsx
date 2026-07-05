"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronLeft, LogOut, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import { navItems } from "./navigation";
import { useAuth } from "@/lib/auth";

export function Sidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 hidden border-r border-border/40 bg-background/90 backdrop-blur-2xl transition-all duration-300 lg:flex lg:flex-col",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <div className="flex h-14 items-center justify-between border-b border-border/40 px-3">
        <Link href="/" className="flex items-center gap-2.5 transition-opacity hover:opacity-85">
          <div className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-[#00E5FF] to-[#8B5CF6] shadow-lg shadow-[#00E5FF]/20">
            <Shield className="size-[18px] text-white" aria-hidden="true" />
          </div>
          {!collapsed && (
            <span className="text-sm font-bold tracking-tight text-text-primary">
              AegisNex
            </span>
          )}
        </Link>
        <button
          className="grid size-7 place-items-center rounded-md text-text-tertiary transition-all hover:bg-surface-elevated hover:text-text-primary"
          type="button"
          onClick={onToggle}
          aria-label="Toggle sidebar"
        >
          <ChevronLeft className={cn("size-3.5 transition-transform duration-300", collapsed && "rotate-180")} />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3 custom-scrollbar">
        <div className="space-y-0.5">
          {navItems.map((item) => {
            const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(`${item.href}/`));
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={cn(
                  "group flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13px] font-medium transition-all duration-200",
                  collapsed && "justify-center px-0",
                  active
                    ? "bg-primary/10 text-primary shadow-sm"
                    : "text-text-secondary hover:bg-surface-elevated hover:text-text-primary",
                )}
              >
                <Icon
                  className={cn(
                    "size-4 shrink-0 transition-all duration-200",
                    active ? "text-primary" : "text-text-tertiary group-hover:text-text-secondary"
                  )}
                  aria-hidden="true"
                />
                {!collapsed && <span className="truncate">{item.label}</span>}
                {!collapsed && active && (
                  <span className="ml-auto block size-1.5 rounded-full bg-primary shadow-sm shadow-primary/50" />
                )}
              </Link>
            );
          })}
        </div>
      </nav>

      <div className="border-t border-border/40 p-2">
        <div className={cn(
          "rounded-lg border border-border/50 bg-surface-elevated/40",
          collapsed ? "p-2" : "p-3"
        )}>
          {!collapsed ? (
            <>
              <div className="mb-2 flex items-center gap-2.5">
                <div className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-[#00E5FF] to-[#8B5CF6] text-[11px] font-bold text-white shadow-sm">
                  A
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-semibold text-text-primary">Operations</p>
                  <p className="truncate text-[10px] text-text-tertiary">Control Plane</p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="flex h-7 w-full items-center gap-2 rounded-md px-2 text-[11px] font-medium text-text-secondary transition-all hover:bg-surface-elevated hover:text-text-primary"
              >
                <LogOut className="size-3" />
                Logout
              </button>
            </>
          ) : (
            <div className="flex size-9 items-center justify-center rounded-lg bg-gradient-to-br from-[#00E5FF] to-[#8B5CF6] text-sm font-bold text-white shadow-sm">
              A
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
