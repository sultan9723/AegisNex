"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { WifiOff, Shield } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const PUBLIC_ROUTES = ["/", "/login", "/login/"];

function LoadingScreen() {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4">
        <div className="relative">
          <div className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 shadow-lg shadow-blue-500/20">
            <Shield className="size-7 text-white" />
          </div>
          <div className="absolute inset-0 animate-ping rounded-2xl bg-blue-500/20" />
        </div>
        <div className="flex items-center gap-2 text-sm text-muted">
          <span className="relative flex size-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-500 opacity-70" />
            <span className="relative inline-flex size-1.5 rounded-full bg-blue-500" />
          </span>
          Loading AegisNex...
        </div>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [isOffline, setIsOffline] = useState(false);

  useEffect(() => {
    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);
    setIsOffline(!navigator.onLine);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  const isPublic = PUBLIC_ROUTES.includes(pathname);
  const isLoginPage = pathname === "/login";

  useEffect(() => {
    if (loading) return;
    if (isAuthenticated && isLoginPage) {
      router.replace("/dashboard");
    } else if (!isAuthenticated && !isPublic) {
      router.replace("/login");
    }
  }, [isAuthenticated, loading, isLoginPage, isPublic, router]);

  if (isPublic) {
    return <>{children}</>;
  }

  if (loading) return <LoadingScreen />;

  if (!isAuthenticated) return null;

  return (
    <div className="relative min-h-screen bg-background text-text-primary">
      {isOffline && (
        <div className="fixed inset-x-0 top-0 z-[100] flex items-center justify-center gap-2 bg-gradient-to-r from-rose-600/90 to-rose-500/90 px-4 py-2 text-sm font-medium text-white shadow-lg backdrop-blur-sm">
          <WifiOff className="size-3.5" />
          You are offline. Some features may be unavailable.
        </div>
      )}
      <div className="fixed inset-0 bg-grid pointer-events-none opacity-50" />
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} />
      <div className={`transition-all duration-300 ease-out-expo ${collapsed ? "lg:pl-16" : "lg:pl-60"}`}>
        <Header />
        <main id="main-content" className="relative mx-auto max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8 animate-fade-in">
          {children}
        </main>
      </div>
    </div>
  );
}
