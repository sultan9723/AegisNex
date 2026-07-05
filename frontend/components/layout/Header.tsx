"use client";

import { useCallback, useEffect, useState } from "react";
import { Bell, Search, User, Settings, LogOut, Mail, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CommandPalette } from "./CommandPalette";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { API_BASE_URL, getNotifications, type NotificationsResponse } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function formatTimestamp(value: unknown): string {
  if (typeof value !== "string") return "\u2014";
  const diff = Date.now() - new Date(value.replace("Z", "+00:00")).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

type NotificationItem = {
  id?: number | string;
  message?: string;
  subject?: string;
  status?: string;
  timestamp?: string;
  provider?: string;
  type?: string;
};

export function Header() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notifLoading, setNotifLoading] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const { user, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const loadNotifications = useCallback(async () => {
    setNotifLoading(true);
    try {
      const res = await getNotifications();
      setNotifications((res.notifications ?? []).slice(0, 5));
    } catch {
      setNotifications([]);
    } finally {
      setNotifLoading(false);
    }
  }, []);

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  const unreadCount = notifications.filter((n) => n.status === "sent" || n.status === "pending").length;

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-border/40 bg-background/80 backdrop-blur-2xl">
        <div className="flex h-14 items-center gap-3 px-4 sm:px-6 lg:px-8">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="group flex h-9 min-w-0 flex-1 items-center gap-3 rounded-lg border border-border bg-surface-elevated/60 px-3 text-sm text-text-secondary transition-all hover:border-border-strong hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 max-w-lg"
          >
            <Search className="size-3.5 shrink-0 text-text-tertiary" />
            <span className="truncate text-[13px]">Search targets, incidents, containers...</span>
            <kbd className="ml-auto hidden rounded-md border border-border bg-surface px-1.5 py-0.5 font-mono text-[10px] font-medium text-text-tertiary sm:inline-flex items-center gap-0.5">
              <span className="text-[9px]">&#8984;</span>K
            </kbd>
          </button>

          <div className="hidden items-center gap-2 rounded-full border border-success/20 bg-success/8 px-3 py-1 text-[11px] font-medium text-success md:flex">
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-70" />
              <span className="relative inline-flex size-1.5 rounded-full bg-success" />
            </span>
            All systems nominal
          </div>

          <DropdownMenu open={notifOpen} onOpenChange={(open) => { setNotifOpen(open); if (open) loadNotifications(); }}>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" className="relative" aria-label="Notifications">
                <Bell className="size-3.5" />
                {unreadCount > 0 && (
                  <span className="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-danger text-[9px] font-bold text-white shadow-sm shadow-danger/50">
                    {unreadCount > 9 ? "9+" : unreadCount}
                  </span>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuLabel>Notifications</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {notifLoading ? (
                <div className="flex items-center justify-center py-6"><Loader2 className="size-4 animate-spin text-text-tertiary" /></div>
              ) : notifications.length === 0 ? (
                <div className="py-6 text-center text-xs text-text-tertiary">No recent notifications</div>
              ) : (
                notifications.map((n, i) => (
                  <DropdownMenuItem key={n.id ?? i} className="flex items-start gap-3 py-2 cursor-default" onSelect={(e) => e.preventDefault()}>
                    <div className="mt-0.5">
                      {n.status === "delivered" || n.status === "sent" ? (
                        <CheckCircle2 className="size-3.5 text-success" />
                      ) : (
                        <XCircle className="size-3.5 text-danger" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium text-text-primary">{n.message ?? n.subject ?? "Notification"}</p>
                      <p className="truncate text-[10px] text-text-tertiary">{formatTimestamp(n.timestamp)}</p>
                    </div>
                  </DropdownMenuItem>
                ))
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => router.push("/notifications")} className="text-xs text-primary justify-center">
                View all notifications
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="User menu">
                <div className="flex size-6 items-center justify-center rounded-full bg-gradient-to-br from-primary/20 to-chart-2/20 text-[11px] font-semibold text-primary ring-1 ring-primary/20">
                  {user?.email?.charAt(0).toUpperCase() ?? "A"}
                </div>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuLabel>
                <div className="truncate text-xs font-medium text-text-primary">{user?.email ?? "Operations"}</div>
                <div className="text-[10px] text-text-tertiary capitalize">{user?.role ?? "admin"}</div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => router.push("/settings")}>
                <Settings className="size-3.5 mr-2" />
                Settings
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogout}>
                <LogOut className="size-3.5 mr-2" />
                Logout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </>
  );
}
