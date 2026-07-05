"use client";

import { useEffect, useRef, useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import { cn } from "@/lib/utils";

type TrendData = { timestamp: string; [key: string]: string | number };

export function TrendChart({
  title,
  data,
  dataKey,
  color = "#00E5FF",
  type = "area",
  className,
}: {
  title: string;
  data: TrendData[];
  dataKey: string;
  color?: string;
  type?: "area" | "bar";
  className?: string;
}) {
  const [chartWidth, setChartWidth] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setChartWidth(containerRef.current.offsetWidth);
      }
    };
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={containerRef}
      className={cn(
        "rounded-xl border border-border/70 bg-surface-elevated/80 p-5 shadow-md",
        "transition-all duration-300 hover:border-border hover:shadow-lg",
        className
      )}
    >
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-[0.08em] text-text-tertiary">
        {title}
      </h3>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          {type === "bar" ? (
            <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border) / 0.5)" vertical={false} />
              <XAxis
                dataKey="timestamp"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "hsl(var(--text-tertiary))", fontSize: 10, fontWeight: 500 }}
                dy={4}
              />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: "hsl(var(--text-tertiary))", fontSize: 10 }} dx={-4} />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--surface-elevated))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                  fontSize: "12px",
                  boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                }}
                labelStyle={{ color: "hsl(var(--text-primary))", fontWeight: 600, marginBottom: 4 }}
                itemStyle={{ color: color }}
              />
              <Bar dataKey={dataKey} fill={color} radius={[3, 3, 0, 0]} maxBarSize={32} />
            </BarChart>
          ) : (
            <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
              <defs>
                <linearGradient id={`gradient-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border) / 0.5)" vertical={false} />
              <XAxis
                dataKey="timestamp"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "hsl(var(--text-tertiary))", fontSize: 10, fontWeight: 500 }}
                dy={4}
              />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: "hsl(var(--text-tertiary))", fontSize: 10 }} dx={-4} />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--surface-elevated))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                  fontSize: "12px",
                  boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                }}
                labelStyle={{ color: "hsl(var(--text-primary))", fontWeight: 600, marginBottom: 4 }}
                itemStyle={{ color: color }}
              />
              <Area
                type="monotone"
                dataKey={dataKey}
                stroke={color}
                strokeWidth={2}
                fill={`url(#gradient-${dataKey})`}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0, fill: color }}
              />
            </AreaChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
