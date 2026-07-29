"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { Shield, ArrowRight, Zap, Menu, X } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { Spinner } from "@/components/common/LoadingState";

const NAV_LINKS = [
  { label: "Product", href: "#capabilities" },
  { label: "Architecture", href: "#architecture" },
  { label: "Integrations", href: "#integrations" },
  { label: "Security", href: "#security" },
];

export function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const { demoLogin } = useAuth();
  const router = useRouter();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [mobileOpen]);

  const handleDemo = async () => {
    setDemoLoading(true);
    try {
      await demoLogin();
      router.push("/dashboard");
    } catch {
      // handled by parent
    } finally {
      setDemoLoading(false);
    }
  };

  return (
    <>
      <header className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${scrolled ? "border-b border-border bg-surface/80 backdrop-blur-2xl shadow-sm" : ""}`}>
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-3 group">
            <div className="relative grid size-8 place-items-center rounded-lg bg-gradient-to-br from-primary to-primary/80 shadow-sm shadow-primary/10 transition-shadow group-hover:shadow-primary/20">
              <Shield className="size-[16px] text-white" strokeWidth={2.5} />
            </div>
            <span className="text-[15px] font-bold tracking-tight text-text-primary">AegisNex</span>
          </Link>
          <nav className="hidden items-center gap-8 md:flex">
            {NAV_LINKS.map((link) => (
              <a key={link.href} href={link.href} className="text-[13px] text-text-tertiary transition-colors hover:text-text-primary">
                {link.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <Link href="/login" className="hidden text-[13px] font-medium text-text-tertiary transition-colors hover:text-text-primary sm:block">
              Sign in
            </Link>
            <button
              onClick={handleDemo}
              disabled={demoLoading}
              className="hidden sm:inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-[13px] font-semibold text-white shadow-sm shadow-primary/20 transition-all hover:bg-primary-hover disabled:opacity-50"
            >
              {demoLoading ? <Spinner className="size-3.5" /> : <Zap className="size-3.5" />}
              {demoLoading ? "Signing in..." : "Get Started"}
              {!demoLoading && <ArrowRight className="size-3.5" />}
            </button>
            <button
              onClick={() => setMobileOpen(true)}
              className="grid size-9 place-items-center rounded-lg border border-border text-text-tertiary hover:text-text-primary md:hidden"
              aria-label="Open menu"
            >
              <Menu className="size-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Mobile drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[60] bg-black/20 backdrop-blur-sm"
              onClick={() => setMobileOpen(false)}
            />
            <motion.div
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", damping: 30, stiffness: 300 }}
              className="fixed inset-y-0 right-0 z-[70] w-72 border-l border-border bg-surface"
            >
              <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <span className="text-[13px] font-bold text-text-primary">Menu</span>
                <button
                  onClick={() => setMobileOpen(false)}
                  className="grid size-7 place-items-center rounded-lg text-text-tertiary hover:text-text-primary"
                  aria-label="Close menu"
                >
                  <X className="size-4" />
                </button>
              </div>
              <nav className="flex flex-col gap-1 p-4">
                {NAV_LINKS.map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    onClick={() => setMobileOpen(false)}
                    className="rounded-lg px-3 py-2.5 text-[13px] text-text-secondary transition-colors hover:bg-muted hover:text-text-primary"
                  >
                    {link.label}
                  </a>
                ))}
                <div className="my-2 h-px bg-border" />
                <a
                  href="/login"
                  className="rounded-lg px-3 py-2.5 text-[13px] text-text-secondary transition-colors hover:bg-muted hover:text-text-primary"
                >
                  Sign in
                </a>
                <button
                  onClick={handleDemo}
                  disabled={demoLoading}
                  className="mt-2 flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-[13px] font-semibold text-white transition-all hover:bg-primary-hover disabled:opacity-50"
                >
                  {demoLoading ? <Spinner className="size-3.5" /> : <Zap className="size-3.5" />}
                  {demoLoading ? "Signing in..." : "Get Started"}
                </button>
              </nav>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
