"use client";

import { useEffect, useState } from "react";
import { Bell, Mail, MessageSquare, Send, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { getNotifications, type NotificationsResponse } from "@/lib/api";
import { API_BASE_URL } from "@/lib/api";
import { SkeletonList } from "@/components/common/Skeleton";
import { toast } from "sonner";

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

export default function NotificationsPage() {
  const [data, setData] = useState<NotificationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [sendingTest, setSendingTest] = useState<string | null>(null);
  useEffect(() => {
    getNotifications().then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, []);

  const stats = data?.notification_stats ?? { email_count: 0, slack_count: 0, discord_count: 0, failed_notifications: 0 };
  const notifications = data?.notifications ?? [];

  const totalSent = stats.email_count + stats.slack_count + stats.discord_count;
  const delivered = Math.max(0, totalSent - stats.failed_notifications);
  const successRate = totalSent > 0 ? Math.round((delivered / totalSent) * 100) : 0;
  const activeChannels = [stats.email_count > 0, stats.slack_count > 0, stats.discord_count > 0].filter(Boolean).length;

  const channelLabel = activeChannels === 0 ? "None" : activeChannels === 1
    ? (stats.email_count > 0 ? "Email" : stats.slack_count > 0 ? "Slack" : "Discord")
    : `${activeChannels} channels`;

  const channelCards = [
    { channelType: "email", icon: Mail, title: "Email", description: "SMTP notification channel", status: (stats.email_count > 0 ? "active" : "inactive") as "active" | "inactive" | "issues", sentCount: String(stats.email_count) },
    { channelType: "slack", icon: MessageSquare, title: "Slack", description: "Slack webhook integration", status: (stats.slack_count > 0 ? "active" : "inactive") as "active" | "inactive" | "issues", sentCount: String(stats.slack_count) },
    { channelType: "discord", icon: MessageSquare, title: "Discord", description: "Discord webhook integration", status: (stats.discord_count > 0 ? "active" : "inactive") as "active" | "inactive" | "issues", sentCount: String(stats.discord_count) },
  ];

  const handleTestNotification = async (channelType: string) => {
    setSendingTest(channelType);
    try {
      const res = await fetch(`${API_BASE_URL}/api/notification-channels/test/${channelType}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const result = await res.json();
      if (result.status === "ok") {
        toast.success(`Test notification sent to ${channelType}`);
      } else {
        toast.error(result.message || `Test notification to ${channelType} failed`);
      }
    } catch {
      toast.error(`Failed to send test notification to ${channelType}`);
    } finally {
      setSendingTest(null);
    }
  };

  const getStatusVariant = (n: Record<string, unknown>) => {
    const s = String(n.status ?? "");
    return s === "delivered" || s === "sent" ? "success-subtle" as const : "danger-subtle" as const;
  };

  const getTypeIcon = (n: Record<string, unknown>) => {
    const p = String(n.provider ?? n.type ?? "email").toLowerCase();
    if (p === "email" || p === "smtp") return Mail;
    return MessageSquare;
  };

  return (
    <RouteScaffold title="Notifications" description="Configure and monitor notification channels including email, Slack, and Discord integrations." icon={Bell}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCardSmall icon={Send} label="Total Sent" value={loading ? "..." : String(totalSent)} detail="Last 24 hours" />
        <MetricCardSmall icon={CheckCircle2} label="Delivered" value={loading ? "..." : String(delivered)} detail={`Success rate: ${totalSent > 0 ? successRate : 0}%`} color="text-success" />
        <MetricCardSmall icon={XCircle} label="Failed" value={loading ? "..." : String(stats.failed_notifications)} detail="Requires attention" color="text-danger" />
        <MetricCardSmall icon={Bell} label="Active Channels" value={loading ? "..." : channelLabel} detail={activeChannels === 0 ? "None configured" : "Email, Slack, Discord"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {channelCards.map((ch) => (
          <ChannelCard
            key={ch.title}
            icon={ch.icon}
            title={ch.title}
            description={ch.description}
            status={ch.status === "active" ? "active" : "issues"}
            sentCount={`${ch.sentCount}`}
            onTest={() => handleTestNotification(ch.channelType)}
            testing={sendingTest === ch.channelType}
          />
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Notifications</CardTitle>
          <p className="mt-0.5 text-xs text-text-secondary">Latest notification delivery attempts</p>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="divide-y divide-border/50">
            {loading && <div className="py-4"><SkeletonList count={5} /></div>}
            {!loading && notifications.length === 0 && <p className="py-6 text-center text-sm text-text-tertiary">No notifications sent yet.</p>}
            {notifications.map((n, idx) => {
              const Icon = getTypeIcon(n);
              const status = String(n.status ?? "unknown");
              const displayStatus = status === "delivered" || status === "sent" ? "delivered" : status;
              return (
                <div key={String(n.id ?? idx)} className="flex items-start justify-between gap-4 py-3.5">
                  <div className="flex items-start gap-3">
                    <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15 mt-0.5">
                      <Icon className="size-3.5" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-text-primary">{String(n.message ?? n.subject ?? "Notification")}</p>
                      <p className="mt-0.5 text-xs text-text-tertiary">To: {String(n.recipient ?? n.service_name ?? "\u2014")} &middot; {formatTimestamp(n.timestamp)}</p>
                    </div>
                  </div>
                  <Badge variant={getStatusVariant(n)} dot>{displayStatus}</Badge>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </RouteScaffold>
  );
}

function MetricCardSmall({ icon: Icon, label, value, detail, color }: { icon: any; label: string; value: string; detail?: string; color?: string }) {
  return (
    <div className="rounded-xl border border-border/40 bg-surface-elevated/40 p-4 transition-all duration-200 hover:border-border/60 hover:bg-surface-elevated/55">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-tertiary">{label}</p>
          <p className={`mt-1 text-2xl font-bold tracking-tight ${color ?? "text-text-primary"}`}>{value}</p>
        </div>
        <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-elevated/80 ring-1 ring-border/50">
          <Icon className="size-3.5 text-text-secondary" />
        </div>
      </div>
      {detail && <p className="mt-2 text-xs text-text-secondary">{detail}</p>}
    </div>
  );
}

function ChannelCard({ icon: Icon, title, description, status, sentCount, onTest, testing }: { icon: any; title: string; description: string; status: "active" | "issues" | "inactive"; sentCount: string; onTest?: () => void; testing?: boolean }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15">
            <Icon className="size-4" />
          </div>
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-text-secondary">Status</span>
            <Badge variant={status === "active" ? "success-subtle" : "warning-subtle"} dot pulse>{status === "active" ? "Active" : "Issues"}</Badge>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-text-secondary">Sent today</span>
            <span className="font-medium text-text-primary">{sentCount}</span>
          </div>
          <Button variant="outline" size="sm" className="w-full" onClick={onTest} disabled={testing}>
            {testing ? <><Loader2 className="size-3.5 mr-1.5 animate-spin" /> Sending...</> : "Test Notification"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
