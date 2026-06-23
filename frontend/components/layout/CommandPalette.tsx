"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Box, FileBarChart, LayoutDashboard, ListChecks, Search, Server, ShieldAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/common/Skeleton";
import { getContainers, getIncidents, getMonitoringTargets, type ContainerRow, type IncidentRow, type MonitoringTarget } from "@/lib/api";
import { cn } from "@/lib/utils";

type PaletteItem = {
  id: string;
  kind: "command" | "target" | "incident" | "container";
  label: string;
  description: string;
  href: string;
  icon: LucideIcon;
  tags: string[];
};

type PaletteData = {
  targets: MonitoringTarget[];
  incidents: IncidentRow[];
  containers: ContainerRow[];
};

const commandItems: PaletteItem[] = [
  { id: "dashboard", kind: "command", label: "Open dashboard", description: "Health score, incidents, and alerts", href: "/dashboard", icon: LayoutDashboard, tags: ["dashboard", "overview", "health"] },
  { id: "targets", kind: "command", label: "Open targets", description: "HTTP, TCP, and SSL monitors", href: "/targets", icon: ListChecks, tags: ["targets", "monitoring", "checks"] },
  { id: "incidents", kind: "command", label: "Open incidents", description: "Active and resolved incidents", href: "/incidents", icon: ShieldAlert, tags: ["incidents", "alerts", "severity"] },
  { id: "containers", kind: "command", label: "Open containers", description: "Runtime status and health", href: "/containers", icon: Box, tags: ["containers", "runtime", "status"] },
  { id: "reports", kind: "command", label: "Open reports", description: "Operational reports and exports", href: "/reports", icon: FileBarChart, tags: ["reports", "exports"] },
];

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<PaletteData | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const load = async () => {
      await Promise.resolve();
      if (controller.signal.aborted) return;
      setLoading(true);
      try {
        const [targets, incidents, containers] = await Promise.all([getMonitoringTargets(), getIncidents(), getContainers()]);
        if (controller.signal.aborted) return;
        setData({
          targets: targets.targets,
          incidents: incidents.incidents,
          containers: containers.containers,
        });
      } catch {
        if (!controller.signal.aborted) setData({ targets: [], incidents: [], containers: [] });
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [open]);

  useEffect(() => {
    if (open) return;
    const timeout = window.setTimeout(() => {
      setQuery("");
      setLoading(false);
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [open]);

  const items = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const corpus: PaletteItem[] = [
      ...commandItems,
      ...(data?.targets ?? []).map((target) => ({
        id: `target-${target.id}`,
        kind: "target" as const,
        label: target.name,
        description: [target.target_type.toUpperCase(), target.address, target.last_error].filter(Boolean).join(" | "),
        href: "/targets",
        icon: ListChecks,
        tags: [target.name, target.address, target.target_type, target.last_error ?? ""],
      })),
      ...(data?.incidents ?? []).map((incident) => ({
        id: `incident-${incident.incident_id}`,
        kind: "incident" as const,
        label: incident.service_name,
        description: [incident.severity, incident.status, incident.description].filter(Boolean).join(" | "),
        href: "/incidents",
        icon: ShieldAlert,
        tags: [incident.service_name, incident.description ?? "", incident.severity, incident.status],
      })),
      ...(data?.containers ?? []).map((container) => ({
        id: `container-${container.name}`,
        kind: "container" as const,
        label: container.name,
        description: [container.status, container.image].filter(Boolean).join(" | "),
        href: "/containers",
        icon: Server,
        tags: [container.name, container.image ?? "", container.status, container.health_status],
      })),
    ];

    if (!normalized) return corpus;
    return corpus.filter((item) => [item.label, item.description, ...item.tags].some((value) => value.toLowerCase().includes(normalized)));
  }, [data, query]);

  const grouped = useMemo(() => {
    const group = {
      command: [] as PaletteItem[],
      target: [] as PaletteItem[],
      incident: [] as PaletteItem[],
      container: [] as PaletteItem[],
    };
    items.forEach((item) => group[item.kind].push(item));
    return group;
  }, [items]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[12vh] max-h-[76vh] max-w-3xl translate-y-0 gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b border-border px-4 py-3">
          <DialogTitle className="flex items-center gap-2 text-sm">
            <Search className="size-4 text-muted-foreground" />
            Global search
          </DialogTitle>
          <DialogDescription className="sr-only">Search dashboards, targets, incidents, and containers.</DialogDescription>
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search targets, incidents, containers"
            className="mt-2 h-10 text-sm"
          />
        </DialogHeader>

        <div className="max-h-[calc(76vh-89px)] overflow-y-auto p-2">
          {loading ? (
            <div className="space-y-2 p-2">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          ) : (
            <>
              {!query && <PaletteGroup title="Commands" items={commandItems} onNavigate={() => onOpenChange(false)} />}
              {query && grouped.command.length > 0 && <PaletteGroup title="Navigation" items={grouped.command} onNavigate={() => onOpenChange(false)} />}
              {grouped.target.length > 0 && <PaletteGroup title={`Targets (${grouped.target.length})`} items={grouped.target} onNavigate={() => onOpenChange(false)} />}
              {grouped.incident.length > 0 && <PaletteGroup title={`Incidents (${grouped.incident.length})`} items={grouped.incident} onNavigate={() => onOpenChange(false)} />}
              {grouped.container.length > 0 && <PaletteGroup title={`Containers (${grouped.container.length})`} items={grouped.container} onNavigate={() => onOpenChange(false)} />}
              {!items.length && (
                <div className="px-4 py-10 text-center">
                  <p className="text-sm font-medium text-foreground">No matches</p>
                  <p className="mt-1 text-sm text-muted-foreground">Try a service name, host, target, or incident.</p>
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PaletteGroup({
  title,
  items,
  onNavigate,
}: {
  title: string;
  items: PaletteItem[];
  onNavigate: () => void;
}) {
  return (
    <section className="px-2 py-1">
      <h3 className="px-2 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">{title}</h3>
      <div className="space-y-1">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.id}
              href={item.href}
              onClick={onNavigate}
              className={cn("flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition hover:bg-white/[0.04] focus-visible:bg-white/[0.04]")}
            >
              <span className="grid size-8 place-items-center rounded-md border border-border bg-muted/60 text-muted-foreground">
                <Icon className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-foreground">{item.label}</span>
                <span className="block truncate text-xs text-muted-foreground">{item.description}</span>
              </span>
              <ArrowRight className="size-4 text-muted-foreground" />
            </Link>
          );
        })}
      </div>
    </section>
  );
}
