"use client";

import { motion } from "framer-motion";
import { Shield, Lock, Fingerprint, Eye, Key, Server, FileBarChart, ShieldCheck, Smartphone } from "lucide-react";

const SECURITY_FEATURES = [
  { icon: Lock, label: "JWT Auth", desc: "Secure token-based auth" },
  { icon: Key, label: "Refresh Tokens", desc: "Seamless session renewal" },
  { icon: Fingerprint, label: "RBAC", desc: "Role-based access control" },
  { icon: Eye, label: "Audit Logs", desc: "Full activity tracking" },
  { icon: Shield, label: "TLS Encryption", desc: "Data in transit protection" },
  { icon: Server, label: "API Keys", desc: "Programmatic access" },
  { icon: Key, label: "Secrets Mgmt", desc: "Encrypted credential store" },
  { icon: FileBarChart, label: "Compliance", desc: "SOC2-ready frameworks" },
  { icon: Smartphone, label: "MFA Ready", desc: "Multi-factor authentication" },
];

export function SecurityGrid() {
  return (
    <section id="security" className="relative py-20 sm:py-28">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="mb-12 text-center"
        >
          <p className="section-eyebrow mb-4">Security</p>
          <h2 className="text-[1.875rem] font-bold tracking-[-0.03em] sm:text-[2.25rem] leading-[1.15] text-text-primary">
            Enterprise-grade from day one
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-[14px] text-text-secondary">
            Built with security-first principles. Every API call authenticated. Every action audited. Every session encrypted.
          </p>
        </motion.div>

        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {SECURITY_FEATURES.map((feat, i) => (
            <motion.div
              key={feat.label}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ delay: i * 0.05, duration: 0.4 }}
              className="group relative flex items-center gap-3 rounded-xl border border-border bg-surface p-4 transition-all duration-300 hover:border-border-strong hover:shadow-md"
            >
              {/* Green pulse */}
              <div className="relative shrink-0">
                <div className="grid size-9 place-items-center rounded-lg bg-success-subtle ring-1 ring-success/15 transition-all duration-300 group-hover:bg-success-bg group-hover:ring-success/25">
                  <feat.icon className="size-4 text-success/60 transition-colors duration-300 group-hover:text-success" />
                </div>
                <span className="absolute -top-0.5 -right-0.5 flex size-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-50" />
                  <span className="relative inline-flex size-1.5 rounded-full bg-success" />
                </span>
              </div>
              <div>
                <p className="text-[13px] font-semibold text-text-primary">{feat.label}</p>
                <p className="text-[11px] text-text-tertiary">{feat.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
