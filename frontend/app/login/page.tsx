"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Shield, Eye, EyeOff, ArrowRight, Zap, Globe, ExternalLink,
  BrainCircuit, Radar, Activity, Lock, ChevronRight, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";

const TOPOLOGY_NODES = [
  { x: 20, y: 28, label: "API Gateway", status: "healthy" as const },
  { x: 50, y: 12, label: "Auth Service", status: "healthy" as const },
  { x: 80, y: 28, label: "AI Engine", status: "healthy" as const },
  { x: 35, y: 52, label: "Database", status: "healthy" as const },
  { x: 65, y: 52, label: "Cache", status: "healthy" as const },
  { x: 50, y: 72, label: "Monitor", status: "healthy" as const },
];

const TOPOLOGY_EDGES: [number, number][] = [
  [0, 1], [1, 2], [0, 3], [2, 4], [3, 5], [4, 5], [1, 5],
];

const FEATURES = [
  { icon: BrainCircuit, label: "AI Copilot", desc: "Natural language ops" },
  { icon: Radar, label: "Auto-Remediation", desc: "Self-healing infra" },
  { icon: Activity, label: "Live Monitoring", desc: "Real-time health" },
  { icon: Shield, label: "Enterprise Security", desc: "RBAC + audit log" },
];

function Spinner({ className = "size-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
    </svg>
  );
}

function TopologyVisualization() {
  return (
    <div className="relative size-full overflow-hidden rounded-2xl border border-border bg-surface/80 backdrop-blur-sm">
      <div className="absolute inset-0 bg-grid-fine opacity-20" />
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[200px] w-[300px] rounded-full bg-blue-500/[0.03] blur-[60px]" />
      <div className="absolute bottom-1/3 left-1/3 h-[150px] w-[200px] rounded-full bg-violet-500/[0.02] blur-[50px]" />

      <svg viewBox="0 0 100 84" className="relative size-full">
        <defs>
          <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="hsl(217 91% 60%)" stopOpacity="0.15" />
            <stop offset="100%" stopColor="hsl(217 91% 60%)" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="edgeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="hsl(217 91% 60%)" stopOpacity="0.12" />
            <stop offset="50%" stopColor="hsl(217 91% 60%)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="hsl(217 91% 60%)" stopOpacity="0.12" />
          </linearGradient>
        </defs>

        {TOPOLOGY_EDGES.map(([from, to], i) => (
          <line
            key={`edge-${i}`}
            x1={TOPOLOGY_NODES[from].x}
            y1={TOPOLOGY_NODES[from].y}
            x2={TOPOLOGY_NODES[to].x}
            y2={TOPOLOGY_NODES[to].y}
            stroke="url(#edgeGrad)"
            strokeWidth="0.25"
            strokeDasharray="1.5 1.5"
          >
            <animate
              attributeName="stroke-dashoffset"
              from="0"
              to="-3"
              dur={`${3 + i * 0.4}s`}
              repeatCount="indefinite"
            />
          </line>
        ))}

        {TOPOLOGY_EDGES.slice(0, 5).map(([from, to], i) => (
          <g key={`packet-${i}`}>
            <circle r="0.5" fill="hsl(217 91% 60%)" opacity="0.6">
              <animateMotion
                dur={`${2.2 + i * 0.25}s`}
                repeatCount="indefinite"
                begin={`${i * 0.4}s`}
                path={`M${TOPOLOGY_NODES[from].x},${TOPOLOGY_NODES[from].y} L${TOPOLOGY_NODES[to].x},${TOPOLOGY_NODES[to].y}`}
              />
            </circle>
            <circle r="1.5" fill="hsl(217 91% 60%)" opacity="0.06">
              <animateMotion
                dur={`${2.2 + i * 0.25}s`}
                repeatCount="indefinite"
                begin={`${i * 0.4}s`}
                path={`M${TOPOLOGY_NODES[from].x},${TOPOLOGY_NODES[from].y} L${TOPOLOGY_NODES[to].x},${TOPOLOGY_NODES[to].y}`}
              />
            </circle>
          </g>
        ))}

        {TOPOLOGY_NODES.map((node, i) => (
          <g key={`node-${i}`}>
            <circle cx={node.x} cy={node.y} r="6" fill="url(#nodeGlow)" opacity="0.4">
              <animate
                attributeName="opacity"
                values="0.2;0.5;0.2"
                dur="4s"
                repeatCount="indefinite"
                begin={`${i * 0.6}s`}
              />
            </circle>
            <circle
              cx={node.x}
              cy={node.y}
              r="2.8"
              fill="none"
              stroke="hsl(217 91% 60% / 0.15)"
              strokeWidth="0.2"
            />
            <circle
              cx={node.x}
              cy={node.y}
              r="2"
              fill="hsl(0 0% 100%)"
              stroke="hsl(217 91% 60% / 0.25)"
              strokeWidth="0.3"
            />
            <circle cx={node.x} cy={node.y} r="0.7" fill="hsl(217 91% 60%)">
              <animate
                attributeName="opacity"
                values="0.5;1;0.5"
                dur="3s"
                repeatCount="indefinite"
                begin={`${i * 0.5}s`}
              />
            </circle>
            <text
              x={node.x}
              y={node.y + 4.8}
              textAnchor="middle"
              fill="hsl(220 9% 46%)"
              fontSize="1.8"
              fontFamily="Inter, sans-serif"
              fontWeight="500"
            >
              {node.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function FeatureHighlights() {
  return (
    <div className="grid grid-cols-2 gap-2.5">
      {FEATURES.map((f, i) => (
        <div
          key={f.label}
          className="group rounded-xl border border-border bg-surface/60 p-3.5 backdrop-blur-sm transition-all duration-300 hover:border-border-strong hover:bg-surface"
          style={{ animationDelay: `${i * 0.1}s` }}
        >
          <div className="mb-2.5 grid size-8 place-items-center rounded-lg bg-blue-50 ring-1 ring-blue-100 transition-all group-hover:bg-blue-100 group-hover:ring-blue-200">
            <f.icon className="size-4 text-blue-500 transition-colors group-hover:text-blue-600" />
          </div>
          <p className="text-[11px] font-semibold text-text-primary">{f.label}</p>
          <p className="mt-0.5 text-[10px] text-text-tertiary leading-relaxed">{f.desc}</p>
        </div>
      ))}
    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { login, demoLogin, user } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const usernameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    usernameRef.current?.focus();
  }, []);

  useEffect(() => {
    if (user) router.replace("/dashboard");
  }, [user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid credentials. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleDemoLogin = useCallback(async () => {
    setError("");
    setDemoLoading(true);
    try {
      await demoLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo login failed. Is the backend running?");
    } finally {
      setDemoLoading(false);
    }
  }, [demoLogin]);

  const isBusy = loading || demoLoading;

  return (
    <div className="relative flex min-h-screen bg-background">
      {/* Left panel - Visualization (55%) */}
      <div className="relative hidden w-[55%] overflow-hidden lg:flex lg:flex-col">
        <div className="absolute inset-0 bg-gradient-to-br from-background via-surface to-background" />
        <div className="absolute inset-0 bg-grid opacity-15" />
        <div className="absolute top-[15%] left-[20%] h-[450px] w-[450px] rounded-full bg-blue-500/[0.02] blur-[120px]" />
        <div className="absolute bottom-[10%] right-[15%] h-[350px] w-[350px] rounded-full bg-violet-500/[0.02] blur-[100px]" />

        <div className="relative z-10 flex flex-1 flex-col justify-between p-10 xl:p-12">
          <Link href="/" className="flex items-center gap-3 self-start group">
            <div className="relative grid size-9 place-items-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 shadow-lg shadow-blue-500/15 transition-shadow group-hover:shadow-blue-500/25">
              <Shield className="size-[18px] text-white" strokeWidth={2.5} />
              <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-white/10 to-transparent" />
            </div>
            <div>
              <span className="text-base font-bold tracking-tight text-text-primary">AegisNex</span>
              <span className="block text-[9px] font-medium uppercase tracking-[0.2em] text-text-tertiary">Infrastructure Intelligence</span>
            </div>
          </Link>

          <div className="mx-auto w-full max-w-lg flex-1 py-6">
            <TopologyVisualization />
          </div>

          <div className="max-w-md space-y-6">
            <FeatureHighlights />
            <div>
              <p className="text-[13px] leading-relaxed text-text-secondary">
                AI-native infrastructure intelligence. Monitor, analyze, and autonomously remediate your entire stack from a single command center.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Right panel - Login (45%) */}
      <div className="flex w-full flex-col justify-center bg-background px-6 sm:px-10 lg:w-[45%] lg:px-14 xl:px-16">
        <div className="mx-auto w-full max-w-[340px]">
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <div className="relative grid size-9 place-items-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 shadow-lg shadow-blue-500/15">
              <Shield className="size-[18px] text-white" strokeWidth={2.5} />
            </div>
            <span className="text-base font-bold tracking-tight text-text-primary">AegisNex</span>
          </div>

          <div className="mb-8">
            <h1 className="mb-2 text-[26px] font-bold tracking-[-0.03em] text-text-primary">
              Welcome back
            </h1>
            <p className="text-[13px] text-text-secondary">
              Sign in to your workspace
            </p>
          </div>

          <button
            type="button"
            onClick={handleDemoLogin}
            disabled={isBusy}
            className="group relative mb-7 flex h-[46px] w-full items-center justify-center gap-2.5 overflow-hidden rounded-xl border border-blue-200 bg-blue-50 text-[13px] font-semibold text-blue-600 transition-all duration-300 hover:border-blue-300 hover:bg-blue-100 hover:shadow-md hover:shadow-blue-500/10 disabled:opacity-50"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-blue-500/0 via-blue-500/[0.04] to-blue-500/0 opacity-0 transition-opacity group-hover:opacity-100" />
            {demoLoading ? (
              <Spinner className="size-4" />
            ) : (
              <Zap className="size-4 transition-transform group-hover:scale-110" />
            )}
            <span className="relative">{demoLoading ? "Signing in..." : "Try Demo Workspace"}</span>
            {!demoLoading && <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />}
          </button>

          <div className="relative mb-7">
            <div className="absolute inset-0 flex items-center">
              <div className="h-px w-full bg-gradient-to-r from-transparent via-border to-transparent" />
            </div>
            <div className="relative flex justify-center text-[11px]">
              <span className="bg-background px-3 text-text-tertiary">or continue with credentials</span>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            <div className="space-y-1.5">
              <label htmlFor="username" className="text-[11px] font-medium text-text-secondary">
                Username
              </label>
              <Input
                ref={usernameRef}
                id="username"
                type="text"
                placeholder="admin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={isBusy}
                autoComplete="username"
                className="h-11 border-border bg-surface text-text-primary placeholder:text-text-disabled focus:border-blue-400 focus:ring-blue-500/10"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="password" className="text-[11px] font-medium text-text-secondary">
                Password
              </label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={isBusy}
                  autoComplete="current-password"
                  className="h-11 border-border bg-surface pr-10 text-text-primary placeholder:text-text-disabled focus:border-blue-400 focus:ring-blue-500/10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary transition-colors hover:text-text-secondary"
                  tabIndex={-1}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between pt-0.5">
              <label className="flex items-center gap-2 text-[12px] text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="size-3.5 rounded border-border bg-surface accent-blue-500"
                />
                Remember me
              </label>
              <button type="button" className="text-[12px] text-text-tertiary transition-colors hover:text-text-secondary">
                Forgot password?
              </button>
            </div>

            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-[12px] text-red-600">
                {error}
              </div>
            )}

            <Button
              type="submit"
              className="relative h-11 w-full overflow-hidden rounded-xl bg-text-primary text-[13px] font-semibold text-background hover:bg-text-primary/90"
              disabled={isBusy}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Spinner className="size-4" />
                  Signing in...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  Sign In
                  <ArrowRight className="size-3.5" />
                </span>
              )}
            </Button>
          </form>

          <div className="mt-10 flex items-center justify-center gap-4 text-[11px] text-text-tertiary">
            <a href="#" className="flex items-center gap-1 transition-colors hover:text-text-secondary">
              <Globe className="size-3" />
              Docs
            </a>
            <span className="text-border">|</span>
            <a href="#" className="flex items-center gap-1 transition-colors hover:text-text-secondary">
              <ExternalLink className="size-3" />
              GitHub
            </a>
          </div>

          <p className="mt-5 text-center text-[10px] text-text-disabled">
            Enterprise SSO available for team plans
          </p>
        </div>
      </div>
    </div>
  );
}
