import {
  Bell,
  Bot,
  Boxes,
  FileBarChart,
  History,
  LayoutDashboard,
  ListChecks,
  Plug,
  Search,
  Server,
  Settings,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
};

export const navItems: NavItem[] = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Search", href: "/search", icon: Search },
  { label: "Infrastructure", href: "/infrastructure", icon: Server },
  { label: "Targets", href: "/targets", icon: ListChecks },
  { label: "Containers", href: "/containers", icon: Boxes },
  { label: "Incidents", href: "/incidents", icon: ShieldAlert },
  { label: "Audit Logs", href: "/audit", icon: History },
  { label: "Reports", href: "/reports", icon: FileBarChart },
  { label: "Notifications", href: "/notifications", icon: Bell },
  { label: "AI Ops", href: "/ai", icon: Sparkles },
  { label: "MCP", href: "/mcp", icon: Bot },
  { label: "Integrations", href: "/integrations", icon: Plug },
  { label: "Settings", href: "/settings", icon: Settings },
];
