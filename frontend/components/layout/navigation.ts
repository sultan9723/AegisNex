import {
  Bell,
  Bot,
  Boxes,
  Activity,
  Building2,
  ClipboardCheck,
  FileBarChart,
  History,
  LayoutDashboard,
  ListChecks,
  Plug,
  Search,
  Server,
  Settings,
  ShieldAlert,
  Shield,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  section?: string;
};

export const navSections = [
  {
    label: "Command Center",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { label: "Clients", href: "/clients", icon: Building2 },
      { label: "Incidents", href: "/incidents", icon: ShieldAlert },
      { label: "Approvals", href: "/approvals", icon: ClipboardCheck },
      { label: "Mission Control", href: "/mission-control", icon: Activity },
    ],
  },
  {
    label: "AI Remediation",
    items: [
      { label: "AI Workspace", href: "/ai", icon: Sparkles },
      { label: "Governance", href: "/governance", icon: Shield },
      { label: "Audit Logs", href: "/audit", icon: History },
    ],
  },
  {
    label: "Advanced Operations",
    items: [
      { label: "Infrastructure", href: "/infrastructure", icon: Server },
      { label: "Targets", href: "/targets", icon: ListChecks },
      { label: "Containers", href: "/containers", icon: Boxes },
    ],
  },
  {
    label: "Advanced",
    items: [
      { label: "Search", href: "/search", icon: Search },
      { label: "Reports", href: "/reports", icon: FileBarChart },
      { label: "Integrations", href: "/integrations", icon: Plug },
      { label: "MCP Tools", href: "/mcp", icon: Bot },
      { label: "Notifications", href: "/notifications", icon: Bell },
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

export const navItems: NavItem[] = navSections.flatMap((s) =>
  s.items.map((i) => ({ ...i, section: s.label })),
);
