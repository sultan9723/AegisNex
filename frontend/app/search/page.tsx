"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import {
  Search,
  FileText,
  Container,
  Shield,
  ShieldAlert,
  Crosshair,
  ScrollText,
  BookOpen,
  Bot,
  Settings,
  Puzzle,
  Library,
  GitBranch,
  Loader2,
  SearchX,
  Command,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { SkeletonList } from "@/components/common/Skeleton";
import { EmptyStateSearch } from "@/components/common/EmptyState";
import { searchEnterprise, type SearchResult, type SearchResponse } from "@/lib/api";

const DOMAIN_ICONS: Record<string, React.ElementType> = {
  incidents: ShieldAlert,
  targets: Crosshair,
  reports: FileText,
  audit_logs: ScrollText,
  runbooks: BookOpen,
  ai_conversations: Bot,
  settings: Settings,
  containers: Container,
  integrations: Puzzle,
  knowledge: Library,
  compliance: Shield,
  workflows: GitBranch,
};

const DOMAIN_LABELS: Record<string, string> = {
  incidents: "Incidents",
  targets: "Targets",
  reports: "Reports",
  audit_logs: "Audit Logs",
  runbooks: "Runbooks",
  ai_conversations: "AI Conversations",
  settings: "Settings",
  containers: "Containers",
  integrations: "Integrations",
  knowledge: "Knowledge",
  compliance: "Compliance",
  workflows: "Workflows",
};

const DOMAIN_COLORS: Record<string, string> = {
  incidents: "danger-subtle",
  targets: "info-subtle",
  reports: "success-subtle",
  audit_logs: "warning-subtle",
  runbooks: "info-subtle",
  ai_conversations: "success-subtle",
  settings: "secondary",
  containers: "info-subtle",
  integrations: "warning-subtle",
  knowledge: "success-subtle",
  compliance: "danger-subtle",
  workflows: "info-subtle",
};

function getDomainIcon(domain: string) {
  return DOMAIN_ICONS[domain] ?? Search;
}

function getDomainLabel(domain: string) {
  return DOMAIN_LABELS[domain] ?? domain;
}

function getDomainBadgeVariant(domain: string) {
  return (DOMAIN_COLORS[domain] ?? "secondary") as "danger-subtle" | "warning-subtle" | "info-subtle" | "success-subtle" | "secondary";
}

function highlightText(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${escaped})`, "gi"));
  return parts.map((part, i) =>
    part.toLowerCase() === query.toLowerCase()
      ? <mark key={i} className="rounded-sm bg-primary/20 px-0.5 text-primary-foreground">{part}</mark>
      : part,
  );
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [domains, setDomains] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [durationMs, setDurationMs] = useState(0);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setDebouncedQuery("");
      return;
    }
    debounceRef.current = setTimeout(() => setDebouncedQuery(query), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      setDomains({});
      setTotal(0);
      setDurationMs(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    setHasSearched(true);
    try {
      const res: SearchResponse = await searchEnterprise(q);
      setResults(res.results ?? []);
      setDomains(res.domains ?? {});
      setTotal(res.total ?? 0);
      setDurationMs(res.duration_ms ?? 0);
    } catch {
      setResults([]);
      setDomains({});
      setTotal(0);
      setDurationMs(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    doSearch(debouncedQuery);
  }, [debouncedQuery, doSearch]);

  const groupedResults = results.reduce<Record<string, SearchResult[]>>((acc, r) => {
    if (!acc[r.domain]) acc[r.domain] = [];
    acc[r.domain].push(r);
    return acc;
  }, {});

  const domainEntries = Object.entries(groupedResults).sort(
    ([, a], [, b]) => b[0].score - a[0].score,
  );

  return (
    <RouteScaffold title="Enterprise Search" description="Search across all domains — incidents, targets, containers, AI conversations, and more." icon={Search}>
      <Card className="sticky top-0 z-10">
        <CardContent className="p-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-tertiary" />
            <Input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search everything... (Cmd+K)"
              className="pl-9 pr-20 text-base"
              autoFocus
            />
            <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 items-center gap-1 rounded-md border border-border bg-surface px-1.5 py-0.5 text-[11px] text-text-tertiary sm:flex">
              <Command className="size-3" />
              <span>K</span>
            </kbd>
          </div>
          {durationMs > 0 && (
            <p className="mt-2 text-[11px] text-text-tertiary">
              Found {total} result{total !== 1 ? "s" : ""} in {durationMs}ms
              {Object.keys(domains).length > 0 && (
                <> across {Object.entries(domains).map(([d, c]) => `${getDomainLabel(d)} (${c})`).join(", ")}</>
              )}
            </p>
          )}
        </CardContent>
      </Card>

      {loading && <SkeletonList count={6} />}

      {!loading && hasSearched && query.trim() && total === 0 && (
        <EmptyStateSearch onClear={() => setQuery("")} />
      )}

      {!loading && !hasSearched && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="mb-4 grid size-16 place-items-center rounded-2xl bg-primary/8 ring-1 ring-primary/15">
            <Search className="size-7 text-primary" />
          </div>
          <h3 className="mb-1 text-lg font-semibold text-text-primary">Search across all domains</h3>
          <p className="max-w-md text-sm text-text-secondary">
            Use the search box above to find incidents, monitoring targets, containers, reports,
            audit logs, runbooks, AI conversations, settings, integrations, knowledge, compliance rules, and workflows.
          </p>
        </div>
      )}

      {!loading && domainEntries.map(([domain, domainResults]) => (
        <Card key={domain} className="overflow-hidden">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <div className="grid size-7 place-items-center rounded-md bg-primary/8 text-primary">
                {React.createElement(getDomainIcon(domain), { className: "size-3.5" })}
              </div>
              <CardTitle className="text-sm">{getDomainLabel(domain)}</CardTitle>
              <Badge variant={getDomainBadgeVariant(domain)} size="sm">{domainResults.length}</Badge>
            </div>
          </CardHeader>
          <CardContent className="divide-y divide-border/30 pt-0">
            {domainResults.map((r) => (
              <a
                key={`${r.domain}:${r.id}`}
                href={r.url}
                className="flex flex-col gap-1 py-3 transition-colors hover:bg-surface-elevated/50 first:pt-0 last:pb-0"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-medium text-text-primary">
                    {highlightText(r.title, debouncedQuery)}
                  </p>
                  <Badge
                    variant={getDomainBadgeVariant(r.domain)}
                    size="sm"
                    className="shrink-0"
                  >
                    {getDomainLabel(r.domain)}
                  </Badge>
                </div>
                {r.snippet && (
                  <p className="line-clamp-2 text-xs text-text-secondary">
                    {highlightText(r.snippet, debouncedQuery)}
                  </p>
                )}
                <p className="text-[11px] text-text-tertiary">{r.url}</p>
              </a>
            ))}
          </CardContent>
        </Card>
      ))}
    </RouteScaffold>
  );
}
