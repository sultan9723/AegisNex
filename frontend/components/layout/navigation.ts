import {
  Bell,
  Bot,
  Boxes,
  FileBarChart,
  LayoutDashboard,
  ListChecks,
  Plug,
  Server,
  Settings,
  ShieldAlert,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
};

export const navItems: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { label: "Infrastructure", href: "/infrastructure", icon: Server },
  { label: "Targets", href: "/targets", icon: ListChecks },
  { label: "Containers", href: "/containers", icon: Boxes },
  { label: "Incidents", href: "/incidents", icon: ShieldAlert },
  { label: "Reports", href: "/reports", icon: FileBarChart },
  { label: "Notifications", href: "/notifications", icon: Bell },
  { label: "MCP", href: "/mcp", icon: Bot },
  { label: "Integrations", href: "/integrations", icon: Plug },
  { label: "Settings", href: "/settings", icon: Settings },
];
