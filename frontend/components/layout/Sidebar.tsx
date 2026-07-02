"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronLeft, LogOut, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import { navItems } from "./navigation";

export function Sidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 hidden border-r border-border bg-card/90 transition-all duration-200 lg:flex lg:flex-col",
        collapsed ? "w-16" : "w-64",
      )}
    >
      <div className="flex h-16 items-center justify-between border-b border-border px-3">
        <Link href="/dashboard" className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-md border border-border bg-background text-primary">
            <Shield className="size-4" aria-hidden="true" />
          </span>
          {!collapsed && <span className="text-sm font-semibold text-foreground">AegisNex</span>}
        </Link>
        <button
          className="grid size-7 place-items-center rounded-md text-muted-foreground transition hover:bg-white/[0.04] hover:text-foreground"
          type="button"
          onClick={onToggle}
          aria-label="Toggle sidebar"
        >
          <ChevronLeft className={cn("size-4 transition", collapsed && "rotate-180")} />
        </button>
      </div>

      <nav className="flex-1 space-y-1 px-2 py-3">
        {navItems.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                "flex h-9 items-center gap-2 rounded-md px-2 text-sm font-medium text-muted-foreground transition hover:bg-white/[0.04] hover:text-foreground",
                active && "bg-primary/10 text-foreground ring-1 ring-primary/20",
                collapsed && "justify-center",
              )}
            >
              <Icon className="size-4 shrink-0" aria-hidden="true" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border p-2">
        <div className={cn("rounded-lg border border-border bg-background/70 p-2", collapsed && "p-1")}>
          {!collapsed ? (
            <>
              <p className="truncate text-xs font-medium text-foreground">Operations workspace</p>
              <p className="truncate text-[11px] text-muted-foreground">AegisNex control plane</p>
              <button type="button" className="mt-2 flex h-7 w-full items-center gap-2 rounded-md px-2 text-xs text-muted-foreground hover:bg-white/[0.04] hover:text-foreground">
                <LogOut className="size-3.5" />
                Logout
              </button>
            </>
          ) : (
            <div className="grid size-8 place-items-center rounded-md bg-primary/10 text-xs font-semibold text-primary">
              A
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
